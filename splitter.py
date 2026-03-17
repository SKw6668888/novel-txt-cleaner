"""
splitter.py — 大文件 TXT 智能切割模块

读取几百万字的中文网文 TXT → 编码检测转 UTF-8 → 按章节切割 → 保存切割块到文件夹。
"""

from __future__ import annotations

import re
from pathlib import Path

import charset_normalizer

# ────────────────────── 常量 ──────────────────────

CHUNK_MAX = 6500               # 单章过长时，按句子再切的上限（字符）
CHINESE_NUMS = "一二三四五六七八九十百千万零"
CHAPTER_PATTERN = re.compile(
    r"^(?:第[" + CHINESE_NUMS + r"0-9]+[章节]|楔子|序章|番外|引子|正文|卷[" + CHINESE_NUMS + r"0-9]+)[\s　]*",
    re.MULTILINE,
)

# 中文分句正则：在 。！？… 后切开，但不在后引号 " 」 前切（lookbehind 须固定宽度）
_SENT_SPLIT_RE = re.compile(r'(?<=[。！？…])(?!["」])\s*')


# ────────────────────── 编码检测 ──────────────────────

def read_file_as_utf8(file_path: Path) -> str:
    """读取任意编码的文本文件，返回 UTF-8 字符串。"""
    raw = file_path.read_bytes()

    result = charset_normalizer.from_bytes(raw).best()
    if result is not None:
        return str(result)

    for fallback in ("utf-8", "gbk", "gb18030", "big5"):
        try:
            return raw.decode(fallback)
        except (UnicodeDecodeError, LookupError):
            continue

    return raw.decode("utf-8", errors="replace")


# ────────────────────── 章节检测 ──────────────────────

def find_chapter_starts(text: str) -> list[tuple[int, str]]:
    """找出所有章节起始位置及标题，返回 [(start_pos, title), ...]。"""
    matches: list[tuple[int, str]] = []
    for m in CHAPTER_PATTERN.finditer(text):
        matches.append((m.start(), m.group(0).strip()))
    return matches


def split_into_chapters(text: str) -> list[tuple[str, str]]:
    """按章节切分文本，返回 [(章节标题, 内容), ...]。"""
    matches = find_chapter_starts(text)
    if not matches:
        return [("全文", text)]

    chapters: list[tuple[str, str]] = []
    # 第一个章节标记之前的内容作为序言
    if matches[0][0] > 0:
        prelude = text[: matches[0][0]].strip()
        if prelude:
            chapters.append(("序言", prelude))

    for i, (pos, title) in enumerate(matches):
        start = pos
        end = matches[i + 1][0] if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        if content:
            chapters.append((title, content))
    return chapters


# ────────────────────── 分句（用于过长章节再切） ──────────────────────

def split_into_sentences(text: str) -> list[str]:
    """将长文本按中文标点拆成句子列表。"""
    parts = _SENT_SPLIT_RE.split(text)
    return [s for s in parts if s]


def split_long_chapter(content: str, max_chars: int = CHUNK_MAX) -> list[str]:
    """章节过长时，按句子边界再切为多个块。"""
    if len(content) <= max_chars:
        return [content]

    sentences = split_into_sentences(content)
    chunks: list[str] = []
    buf: list[str] = []
    char_count = 0

    for s in sentences:
        slen = len(s)
        if char_count + slen > max_chars and buf:
            chunks.append("".join(buf))
            buf = []
            char_count = 0
        buf.append(s)
        char_count += slen

    if buf:
        chunks.append("".join(buf))
    return chunks


# ────────────────────── 保存 ──────────────────────

def save_chunks(
    chunks: list[tuple[str, str]],
    stem: str,
    output_dir: Path,
) -> list[str]:
    """将切割块写入磁盘，返回所有文件的绝对路径列表。

    chunks: [(块标题, 内容), ...]
    """
    sub_dir = output_dir / stem
    sub_dir.mkdir(parents=True, exist_ok=True)

    total = len(chunks)
    paths: list[str] = []
    char_offset = 0

    for i, (title, content) in enumerate(chunks, start=1):
        fname = f"{stem}_chunk_{i:03d}.txt"
        fpath = sub_dir / fname

        header = (
            f"# chunk {i}/{total} | {title} "
            f"| start_char: {char_offset} | length: {len(content)}\n\n"
        )
        fpath.write_text(header + content, encoding="utf-8")

        abs_path = str(fpath.resolve())
        paths.append(abs_path)
        print(f"保存块 {i}/{total}：{fname} ({len(content)} 字符) [{title[:20]}...]")

        char_offset += len(content)

    return paths


# ────────────────────── 主入口 ──────────────────────

def split_large_txt(
    input_file_path: str,
    output_dir: str = "chunks_output",
) -> list[str]:
    """读取大 TXT → 编码转换 → 按章节切割 → 保存到文件夹。

    - 按章节边界切割（第X章、楔子、序章等）。
    - 单章超过 CHUNK_MAX 字符时，按句子再切。
    """
    src = Path(input_file_path)
    if not src.is_file():
        raise FileNotFoundError(f"文件不存在：{src}")

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    print(f"读取文件：{src}（{src.stat().st_size / 1024 / 1024:.1f} MB）")
    text = read_file_as_utf8(src)
    print(f"读取完成，共 {len(text)} 字符")

    chapters = split_into_chapters(text)
    print(f"检测到 {len(chapters)} 个章节")

    # 每章若过长则再切
    chunks: list[tuple[str, str]] = []
    for title, content in chapters:
        sub_chunks = split_long_chapter(content)
        for j, sub in enumerate(sub_chunks):
            sub_title = f"{title}_part{j + 1}" if len(sub_chunks) > 1 else title
            chunks.append((sub_title, sub))

    paths = save_chunks(chunks, src.stem, out)
    return paths


# ────────────────────── CLI ──────────────────────

if __name__ == "__main__":
    import os
    import sys
    base = os.path.dirname(os.path.abspath(__file__))
    input_file = os.path.join(base, "test_novel.txt") if len(sys.argv) < 2 else sys.argv[1]
    try:
        paths = split_large_txt(input_file)
        print(f"\n切割完成，共生成 {len(paths)} 个块文件")
    except Exception as e:
        print(f"出错：{e}")
