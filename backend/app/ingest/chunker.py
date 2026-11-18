"""Markdown 切片:按标题+段落切,每 chunk 带 heading_path 与行号定位(技术总纲 2.5)。"""

import re
from dataclasses import dataclass

_HEADING = re.compile(r"^(#{1,6})\s+(.+)$")
MAX_CHARS = 1200

# shortcut: 阈值固定写死,无自适应分块;内容超长导致检索粒度变差时再升级


@dataclass
class Chunk:
    content: str
    heading_path: str
    start_line: int
    end_line: int


def chunk_markdown(md: str, max_chars: int = MAX_CHARS) -> list[Chunk]:
    lines = md.splitlines()
    chunks: list[Chunk] = []
    heading_stack: list[str] = []
    buf: list[str] = []
    buf_start = 1
    current_path = ""

    def flush(end_line: int) -> None:
        nonlocal buf, buf_start
        text = "\n".join(buf).strip()
        if text:
            chunks.append(Chunk(content=text, heading_path=current_path,
                                start_line=buf_start, end_line=end_line))
        buf = []
        buf_start = end_line + 1

    for i, line in enumerate(lines, start=1):
        m = _HEADING.match(line)
        if m:
            level, title = len(m.group(1)), m.group(2).strip()
            # 一级/二级标题开新块,更深标题留在块内继续累积
            if level <= 2:
                flush(i - 1)
                heading_stack = heading_stack[: level - 1]
                heading_stack.append(title)
                current_path = " > ".join(heading_stack)
                buf_start = i
            buf.append(line)
            continue
        if len(line) > max_chars:
            # 超长单行(无换行的长段落):并入缓冲后整体硬切
            text = "\n".join([*buf, line])
            for s in range(0, len(text), max_chars):
                chunks.append(
                    Chunk(content=text[s : s + max_chars], heading_path=current_path,
                          start_line=buf_start, end_line=i)
                )
            buf = []
            buf_start = i + 1
            continue
        buf.append(line)
        if sum(len(b) + 1 for b in buf) >= max_chars:
            flush(i)
    flush(len(lines))
    return chunks
