"""文本读取与规范化（编码、空白）。"""

from __future__ import annotations

import re

from app.core.errors import Validation

_MULTI_BLANK = re.compile(r"\n{3,}")
_TRAILING_WS = re.compile(r"[ \t\u3000]+$", re.M)


def read_text_bytes(data: bytes) -> str:
    """utf-8（含 BOM）→ gb18030 → utf-16（BOM）。失败给可读错误。"""
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    for enc in ("utf-8", "gb18030"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise Validation("无法识别文本编码（支持 UTF-8 / GB18030 / UTF-16）")


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _TRAILING_WS.sub("", text)
    text = _MULTI_BLANK.sub("\n\n", text)
    return text.strip("\n")


def split_paragraphs(text: str, line_offset: int = 0) -> list[tuple[str, int, int]]:
    """按空行分段，返回 (段文本, 起始行, 结束行)；行号 1 基。"""
    paragraphs: list[tuple[str, int, int]] = []
    cur_lines: list[str] = []
    start = line_offset + 1
    for i, line in enumerate(text.split("\n"), start=line_offset + 1):
        if line.strip():
            if not cur_lines:
                start = i
            cur_lines.append(line.rstrip())
        elif cur_lines:
            paragraphs.append(("\n".join(cur_lines), start, i - 1))
            cur_lines = []
    if cur_lines:
        paragraphs.append(("\n".join(cur_lines), start, line_offset + len(text.split("\n"))))
    return paragraphs
