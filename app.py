import os
import sys

# PyInstaller -w 模式下 sys.stdout/stderr 为 None，uvicorn 日志会报 isatty 错误
# 必须在 import gradio 之前修复
if getattr(sys, "frozen", False) and (sys.stdout is None or sys.stderr is None):
    class _DummyStream:
        def write(self, *args, **kwargs): pass
        def flush(self, *args, **kwargs): pass
        def isatty(self): return False
        def fileno(self): return -1
    if sys.stdout is None:
        sys.stdout = _DummyStream()
    if sys.stderr is None:
        sys.stderr = _DummyStream()

os.environ["no_proxy"] = "localhost,127.0.0.1"

import gradio as gr
import charset_normalizer
from pathlib import Path

# 打包为 exe 时：输出目录为 exe 所在目录（便于用户找到 chunks_output）
# 不硬编码相对路径，打包后路径会变
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

from splitter import split_large_txt
from cleaner_api import clean_chunks_with_api, get_clean_status, DEFAULT_PROMPT, API_CONFIG


def detect_and_read(file_path: str) -> str:
    """读取文件并自动检测编码，返回 UTF-8 字符串。"""
    raw = Path(file_path).read_bytes()
    result = charset_normalizer.from_bytes(raw).best()
    if result is None:
        raise ValueError("无法检测文件编码，请确认文件是文本格式")
    return str(result)


def preview_text(text: str, limit: int = 1500) -> str:
    """截取前 limit 个字符用于预览。"""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n..."


def on_upload(filepath):
    """文件上传后立即触发：读取内容并刷新原文预览。"""
    if filepath is None:
        return ""
    content = detect_and_read(filepath)
    return preview_text(content)


def get_file_status(filepath):
    """根据当前文件检测切割与清洗状态，返回 (展示文本, 输出目录路径)。"""
    if filepath is None:
        return "", ""
    stem = Path(filepath).stem
    chunk_dir = BASE_DIR / "chunks_output" / stem
    info = get_clean_status(str(chunk_dir))
    msg = f"📋 当前状态：{info['message']}"
    folder = ""
    if info["merged"]:
        msg += f"\n\n合并文件：{info['merged']}"
        folder = str(Path(info["merged"]).parent)
    return msg, folder


def on_split(filepath):
    """点击「切割」后：按章节切割并保存到 chunks_output 文件夹。"""
    if filepath is None:
        return "请先上传 TXT 文件"

    output_dir = BASE_DIR / "chunks_output"
    try:
        paths = split_large_txt(filepath, output_dir=str(output_dir))
        out_folder = output_dir / Path(filepath).stem
        return (
            f"✅ 切割完成！\n"
            f"输出目录：{out_folder}\n"
            f"共生成 {len(paths)} 个块文件\n"
        )
    except Exception as e:
        return f"❌ 切割失败：{e}"


def on_clean(filepath, api_key, api_provider, model, prompt_text, progress=gr.Progress(track_tqdm=False)):
    """点击「开始清洗」后：调用 API 清洗 chunks 目录。"""
    if filepath is None:
        yield "请先上传 TXT 文件", ""
        return

    stem = Path(filepath).stem
    chunk_dir = BASE_DIR / "chunks_output" / stem
    if not chunk_dir.exists():
        yield "请先切割文件", ""
        return

    if not list(chunk_dir.glob("*_chunk_*.txt")):
        yield "未找到切割块文件", ""
        return

    if not api_key or not api_key.strip():
        yield "请先填入 API Key", ""
        return

    def progress_fn(current, total, desc):
        progress(current / total if total else 0, desc=desc)

    yield "正在处理...", ""
    try:
        merged = clean_chunks_with_api(
            str(chunk_dir),
            api_provider=api_provider,
            model=model.strip() or None,
            api_key=api_key.strip() or None,
            system_prompt=prompt_text.strip() or None,
            progress_callback=progress_fn,
        )
        folder = str(Path(merged).parent)
        msg = (
            f"✅ 清洗完成！\n\n"
            f"合并文件位置：\n{merged}\n\n"
            f"👉 点击下方「打开输出文件夹」按钮可直接进入该目录"
        )
        yield msg, folder
    except Exception as e:
        yield f"❌ 清洗失败：{e}", ""


def open_output_folder(folder_path):
    """在资源管理器中打开输出文件夹。"""
    if not folder_path or not Path(folder_path).is_dir():
        gr.Info("请先完成清洗，生成合并文件后再试")
        return
    try:
        os.startfile(folder_path)  # Windows
        gr.Info("已打开文件夹")
    except Exception as e:
        gr.Info(f"打开失败：{e}")


def restore_default_prompt():
    """恢复默认提示词。"""
    return DEFAULT_PROMPT


# ────────────────────────── UI ──────────────────────────

with gr.Blocks(
    theme=gr.themes.Soft(),
    title="网文清洗器",
    css="""
    .main-title  { text-align:center; margin-bottom:0 }
    .sub-title   { text-align:center; color:#888; margin-top:0; font-size:0.95em }
    .status-bar  { font-size:0.85em; color:#aaa }
    /* 隐藏进度条预计时间 */
    .eta, [class*="eta"], .progress-eta { display: none !important; }
    """,
) as app:

    # ── 标题 ──
    gr.Markdown(
        "<h1 class='main-title'>网文清洗器 - v1.0</h1>"
        "<p class='sub-title'>"
        "拖入 TXT 小说文件 → AI 自动去除广告、作者碎碎念、水印，只保留连贯正文（本地运行，无需联网）"
        "</p>"
    )

    # ── API 配置 ──
    with gr.Accordion("🔑 API 配置", open=True):
        with gr.Row():
            api_key_input = gr.Textbox(
                label="API Key",
                placeholder="sk-...（支持多种服务）",
                type="password",
            )
            api_provider = gr.Dropdown(
                label="API 服务",
                choices=[
                    "openai", "claude", "groq", "mistral", "openrouter",
                    "zhipu", "yi", "deepseek", "kimi", "qwen",
                ],
                value="qwen",
            )
            model_dropdown = gr.Dropdown(
                label="模型",
                choices=API_CONFIG["qwen"]["models"],
                value=API_CONFIG["qwen"]["default_model"],
                allow_custom_value=True,
            )

        def update_models(provider):
            cfg = API_CONFIG.get(provider, API_CONFIG["qwen"])
            return gr.update(choices=cfg["models"], value=cfg["default_model"])

        api_provider.change(fn=update_models, inputs=[api_provider], outputs=[model_dropdown])

    # ── 提示词 ──
    with gr.Accordion("✏️ 提示词（可修改）", open=False):
        prompt_box = gr.Textbox(
            label="清洗提示词",
            value=DEFAULT_PROMPT,
            lines=18,
            max_lines=25,
            placeholder="修改后用于 API 清洗，{text} 为待清洗文本占位符",
        )
        prompt_restore_btn = gr.Button("🔄 恢复默认提示词", variant="secondary")

    # ── 上传 ──
    file_input = gr.File(
        label="上传待清洗的小说 TXT 文件（支持单文件，.txt 格式）",
        file_types=[".txt"],
        type="filepath",
    )

    # ── 按钮 ──
    with gr.Row():
        split_btn = gr.Button("📂 切割（按章节）", variant="secondary", size="lg")
        clean_btn = gr.Button("🚀 开始清洗", variant="primary", size="lg")
        open_folder_btn = gr.Button("📂 打开输出文件夹", variant="secondary", size="lg")

    # 存储最近一次清洗完成后的输出目录路径
    output_folder_state = gr.State(value="")

    # ── 预览区 ──
    with gr.Row():
        original_box = gr.Textbox(
            label="原文预览（前 1500 字）",
            lines=14,
            interactive=False,
        )
        status_box = gr.Textbox(
            label="处理状态与输出路径",
            lines=14,
            interactive=False,
        )

    def on_file_change(filepath):
        """文件选择变化时：刷新预览 + 刷新切割/清洗状态。"""
        preview = on_upload(filepath)
        status, folder = get_file_status(filepath)
        return preview, status, folder

    # ── 事件绑定 ──
    file_input.change(
        fn=on_file_change,
        inputs=[file_input],
        outputs=[original_box, status_box, output_folder_state],
    )

    split_btn.click(
        fn=on_split,
        inputs=[file_input],
        outputs=[status_box],
    )

    clean_btn.click(
        fn=on_clean,
        inputs=[file_input, api_key_input, api_provider, model_dropdown, prompt_box],
        outputs=[status_box, output_folder_state],
        show_progress="minimal",
    )

    open_folder_btn.click(
        fn=open_output_folder,
        inputs=[output_folder_state],
        outputs=[],
    )

    prompt_restore_btn.click(
        fn=restore_default_prompt,
        inputs=[],
        outputs=[prompt_box],
    )


if __name__ == "__main__":
    app.launch(server_name="127.0.0.1", inbrowser=True)
