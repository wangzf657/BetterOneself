"""Markdown / TXT 解析（技术方案 §4.2）。"""

from __future__ import annotations

from pathlib import Path

from app.core.errors import Validation
from app.ingest.headings import build_text_book
from app.ingest.textio import normalize_text, read_text_bytes
from app.ingest.types import ParsedBook


def parse_markdown(path: Path) -> ParsedBook:
    text = normalize_text(read_text_bytes(path.read_bytes()))
    nodes, sections = build_text_book(
        text, confidence=0.85, confidence_basis="标题规则识别", source_type="md", md_only=True
    )
    return ParsedBook(
        source_type="md",
        confidence=0.85 if nodes else 0.3,
        confidence_basis="标题规则识别" if nodes else "不确定结构",
        tree_nodes=nodes,
        sections=sections,
    )


def parse_txt(path: Path) -> ParsedBook:
    text = normalize_text(read_text_bytes(path.read_bytes()))
    if not text:
        raise Validation("TXT 文件内容为空，无法导入")
    nodes, sections = build_text_book(
        text, confidence=0.7, confidence_basis="标题规则识别", source_type="txt"
    )
    return ParsedBook(
        source_type="txt",
        confidence=0.7 if nodes else 0.3,
        confidence_basis="标题规则识别" if nodes else "不确定结构",
        tree_nodes=nodes,
        sections=sections,
    )
