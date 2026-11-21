"""ingest 入口：格式识别与解析分发（零 LLM，B2-01）。"""

from __future__ import annotations

from pathlib import Path

from app.core.errors import Validation
from app.ingest.epub_parser import parse_epub
from app.ingest.md_txt import parse_markdown, parse_txt
from app.ingest.pdf_parser import parse_pdf
from app.ingest.types import ParsedBook


def parse_file(path: Path, source_type: str) -> ParsedBook:
    if not path.exists() or path.stat().st_size == 0:
        raise Validation("文件不存在或为空")
    if source_type == "pdf":
        return parse_pdf(path)
    if source_type == "epub":
        return parse_epub(path)
    if source_type == "md":
        return parse_markdown(path)
    if source_type == "txt":
        return parse_txt(path)
    raise Validation(f"不支持的格式：{source_type}")
