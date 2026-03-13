"""
cleaner_api.py — 小说 TXT 分块清洗（OpenAI 兼容 API）

支持 DeepSeek / Moonshot / Qwen 一键切换，遍历 chunk 目录调用 API 清洗并合并。
"""

from __future__ import annotations

import time
from pathlib import Path

from openai import OpenAI

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import os

# ────────────────────── 常量 ──────────────────────

API_CONFIG = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "models": ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
    },
    "claude": {
        "base_url": "https://api.anthropic.com/v1",
        "default_model": "claude-sonnet-4-20250514",
        "models": ["claude-sonnet-4-20250514", "claude-3-5-sonnet-20241022", "claude-3-opus-20240229"],
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
        "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-120b", "openai/gpt-oss-20b"],
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "default_model": "mistral-large-latest",
        "models": ["mistral-large-latest", "mistral-small-latest", "open-mistral-7b"],
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "anthropic/claude-3.5-sonnet",
        "models": [
            "anthropic/claude-3.5-sonnet",
            "openai/gpt-4o",
            "openai/gpt-4o-mini",
            "google/gemini-pro-1.5",
            "meta-llama/llama-3.1-70b-instruct",
        ],
    },
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "default_model": "glm-4-flash",
        "models": ["glm-4-flash", "glm-4-plus", "glm-4", "glm-4-long"],
    },
    "yi": {
        "base_url": "https://api.lingyiwanwu.com/v1",
        "default_model": "yi-large",
        "models": ["yi-large", "yi-large-turbo", "yi-medium-200k", "yi-34b-chat-200k"],
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-chat",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
    "kimi": {
        "base_url": "https://api.moonshot.cn/v1",
        "default_model": "moonshot-v1-8k",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-turbo",
        "models": ["qwen-turbo", "qwen-plus", "qwen-max", "qwen-long"],
    },
}

DEFAULT_PROMPT = """你是一个严格的小说正文提取器。你的唯一任务是删除广告、作者碎碎念、推广、水印、更新通知、弹窗提示、版权声明等一切不属于小说正文的内容。

非常重要的格式要求（必须严格遵守，违反任何一条都视为严重错误）：

1. 绝对不要改变原文的换行和段落结构。
   - 原文中句子之间的换行必须完全保留。
   - 原文中的空行（段落分隔）必须完全保留。
   - 原文中的缩进（如果有）必须保留。
   - 不要把多行合并成一行，也不要把一段拆成多段。

2. 只删除整段或整行明显无关的内容，不要改动任何正文句子的内部结构和换行。

3. 输出时：
   - 直接输出清洗后的原文文本，什么前缀、后缀、解释、```markdown 都不要加。
   - 保留原文的所有标点、空格、换行、段落间距。
   - 如果某段被判断为垃圾而删除，则直接移除该整段（包括其前后换行），不要用其他文字填充空位。

4. 判断标准（仅供参考，不要输出）：
   - 属于正文：连贯的叙事、对话、场景描写、人物心理、章节标题（如果想保留）
   - 不属于正文：广告、求票、感谢、题外话、平台推广、二维码、App下载、更新说明等

5. 必须删除所有章节前后出现的以下符号或类似导航标记：
   - &larr; &rarr;、← →、上一章 / 下一章
   - 任何形式的左右箭头、翻页符号、分隔箭头
   即使它们出现在章节标题前后，也一律删除。

现在处理以下文本，直接输出清洗后的结果：

{text}
"""


def _load_prompt() -> str:
    """优先从 prompts/clean_prompt.txt 读取，否则用默认。"""
    p = Path(__file__).parent / "prompts" / "clean_prompt.txt"
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    return DEFAULT_PROMPT


CLEAN_PROMPT = _load_prompt()

MAX_RETRIES = 3
RETRY_DELAY = 5
REQUEST_TIMEOUT = 120


# ────────────────────── API 调用 ──────────────────────

def _get_client(api_provider: str, api_key: str | None) -> tuple[OpenAI, str]:
    """根据 provider 返回 OpenAI 客户端和 model。"""
    provider = api_provider.lower()
    if provider not in API_CONFIG:
        raise ValueError(f"不支持的 api_provider: {api_provider}，可选: openai, claude, deepseek, kimi, qwen")

    cfg = API_CONFIG[provider]
    key = api_key or os.getenv("API_KEY") or os.getenv(f"{provider.upper()}_API_KEY")
    if not key and provider == "claude":
        key = os.getenv("ANTHROPIC_API_KEY")
    if not key and provider == "groq":
        key = os.getenv("GROQ_API_KEY")
    if not key:
        raise ValueError(f"未设置 API_KEY，请在 .env 中配置或传入 api_key 参数")

    base_url = os.getenv("BASE_URL") or cfg["base_url"]
    client = OpenAI(api_key=key, base_url=base_url)
    return client, cfg["default_model"]


def _call_clean_api(
    client: OpenAI,
    model: str,
    text: str,
    system_prompt: str | None = None,
) -> str:
    """调用 API 清洗文本，带重试。"""
    prompt = (system_prompt or CLEAN_PROMPT).replace("{text}", "").strip()
    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text},
                ],
                temperature=0.1,
                stream=False,
                timeout=REQUEST_TIMEOUT,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            last_err = e
            err_str = str(e).lower()
            if "rate" in err_str or "429" in err_str or "limit" in err_str:
                time.sleep(RETRY_DELAY * (attempt + 1))
            elif "timeout" in err_str:
                time.sleep(RETRY_DELAY)
            else:
                raise
    raise last_err


# ────────────────────── 主流程 ──────────────────────

def clean_chunks_with_api(
    chunk_dir: str,
    api_provider: str = "deepseek",
    model: str | None = None,
    api_key: str | None = None,
    system_prompt: str | None = None,
    progress_callback=None,
) -> str:
    """遍历 chunk 目录，调用 API 清洗每个块，合并为完整小说。

    Args:
        chunk_dir: 切割块所在目录（如 chunks_output/dirty_novel/）
        api_provider: deepseek | kimi | qwen
        model: 模型名，不传则用 provider 默认
        api_key: API 密钥，不传则从 .env 读取

    Returns:
        合并后的完整小说文件绝对路径。
    """
    root = Path(chunk_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"目录不存在：{root}")

    chunks = sorted(root.glob("*_chunk_*.txt"))
    if not chunks:
        raise FileNotFoundError(f"未找到 *_chunk_*.txt 文件：{root}")

    client, default_model = _get_client(api_provider, api_key)
    model = model or default_model

    # 推断书名（取第一个 chunk 的 stem 去掉 _chunk_001 等）
    stem = chunks[0].stem
    base_name = stem.rsplit("_chunk_", 1)[0]
    clean_dir = root
    merged_path = root / f"{base_name}_clean.txt"

    cleaned_paths: list[Path] = []
    total_original = 0
    total_cleaned = 0

    total_chunks = len(chunks)
    for i, chunk_path in enumerate(chunks, start=1):
        if progress_callback:
            progress_callback(i - 1, total_chunks, f"清洗中 {i}/{total_chunks}: {chunk_path.name}")

        raw = chunk_path.read_text(encoding="utf-8")
        # 跳过首行元信息注释
        lines = raw.split("\n", 1)
        if lines[0].strip().startswith("#"):
            content = lines[1] if len(lines) > 1 else ""
        else:
            content = raw

        orig_len = len(content)
        total_original += orig_len

        t0 = time.time()
        try:
            cleaned = _call_clean_api(client, model, content, system_prompt)
        except Exception as e:
            print(f"[{i}/{len(chunks)}] ❌ {chunk_path.name} 失败：{e}")
            raise

        elapsed = time.time() - t0
        clean_len = len(cleaned)
        total_cleaned += clean_len
        drop_pct = (1 - clean_len / orig_len) * 100 if orig_len else 0

        out_name = chunk_path.stem.replace("_chunk_", "_clean_") + ".txt"
        out_path = clean_dir / out_name
        out_path.write_text(cleaned, encoding="utf-8")
        cleaned_paths.append(out_path)

        print(f"[{i}/{total_chunks}] ✓ {chunk_path.name} → {out_name} | {elapsed:.1f}s | 删除约 {drop_pct:.1f}%")

        if progress_callback:
            progress_callback(i, total_chunks, f"已完成 {i}/{total_chunks}")

    # 合并
    merged_parts: list[str] = []
    for p in cleaned_paths:
        text = p.read_text(encoding="utf-8")
        merged_parts.append(text)

    if progress_callback:
        progress_callback(total_chunks, total_chunks, "合并中...")

    merged_path.write_text("\n\n".join(merged_parts), encoding="utf-8")
    total_drop = (1 - total_cleaned / total_original) * 100 if total_original else 0

    print(f"\n✅ 合并完成：{merged_path}")
    print(f"   总字符：{total_original} → {total_cleaned}，删除约 {total_drop:.1f}%")

    return str(merged_path.resolve())


# ────────────────────── CLI ──────────────────────

if __name__ == "__main__":
    # 修改为你的切割目录，使用阿里通义 qwen
    clean_chunks_with_api(
        "chunks_output/全职法师2501-3000章/",
        api_provider="qwen",
        model="qwen-turbo",
    )
