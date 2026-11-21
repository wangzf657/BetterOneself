"""纯文本（TXT/Markdown/PDF 降级）的标题结构识别：零 LLM（B2-01）。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.ingest.textio import split_paragraphs
from app.ingest.types import Para, RawSection, TreeNode

RE_ATX = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
RE_ZH_CHAPTER = re.compile(
    r"^第\s*([0-9０-９一二三四五六七八九十百零两]+)\s*([章篇部])(?:\s*[：:．.]?\s*(.*))?$"
)
RE_ZH_SECTION = re.compile(r"^第\s*([0-9０-９一二三四五六七八九十百零两]+)\s*节(?:\s*[：:．.]?\s*(.*))?$")
RE_EN_CHAPTER = re.compile(r"^Chapter\s+(\d+)\s*[.、:：]?\s*(.*)$", re.IGNORECASE)
RE_NUM = re.compile(r"^(\d+(?:\.\d+){0,4})[.、\s]\s*(\S.*)$")

MAX_TITLE_LEN = 60


def detect_heading(line: str, *, md_only: bool = False) -> tuple[int, str] | None:
    """返回 (level, title)；识别不出返回 None。标题必须短、独立成行。"""
    stripped = line.strip()
    if not stripped or len(stripped) > MAX_TITLE_LEN + 20:
        return None
    m = RE_ATX.match(stripped)
    if m:
        title = m.group(2).strip().strip("#").strip()
        return (len(m.group(1)), title) if title else None
    if md_only:
        return None
    m = RE_ZH_CHAPTER.match(stripped)
    if m:
        title = f"第{m.group(1)}{m.group(2)}{_suffix(m.group(3))}"
        return (1, title)
    m = RE_EN_CHAPTER.match(stripped)
    if m and m.group(2).strip():
        return (1, f"Chapter {m.group(1)} {m.group(2).strip()}")
    m = RE_ZH_SECTION.match(stripped)
    if m and m.group(2) and m.group(2).strip():
        return (2, f"第{m.group(1)}节 {m.group(2).strip()}")
    m = RE_NUM.match(stripped)
    if m:
        num, rest = m.group(1), m.group(2).strip()
        if "." not in num and len(num) == 4:  # 年份防误判
            return None
        if rest.endswith(("。", "，", "；", "！", "？")) or len(rest) > MAX_TITLE_LEN:
            return None
        return (num.count(".") + 1, f"{num} {rest}")
    return None


def _suffix(s: str | None) -> str:
    return f" {s.strip()}" if s and s.strip() else ""


@dataclass
class Occurrence:
    order: int
    level: int
    title: str
    line: int


def find_occurrences(
    lines: list[str], *, md_only: bool = False, line_offset: int = 0
) -> list[Occurrence]:
    out: list[Occurrence] = []
    for i, line in enumerate(lines, start=line_offset + 1):
        hit = detect_heading(line, md_only=md_only)
        if hit:
            out.append(Occurrence(order=len(out) + 1, level=hit[0], title=hit[1], line=i))
    return out


def build_text_book(
    text: str,
    *,
    confidence: float,
    confidence_basis: str,
    source_type: str,
    md_only: bool = False,
) -> tuple[list[TreeNode], list[RawSection]]:
    """从纯文本构建树与节。返回 (tree_nodes, sections)。"""
    lines = text.split("\n")
    occs = find_occurrences(lines, md_only=md_only)
    if not occs:
        return [], []

    # 栈式建树：key = 出现序号（唯一），parent = 栈内最近的上层标题
    nodes: list[TreeNode] = []
    stack: list[Occurrence] = []
    sections: list[RawSection] = []
    for idx, occ in enumerate(occs):
        while stack and stack[-1].level >= occ.level:
            stack.pop()
        parent = stack[-1] if stack else None
        nodes.append(
            TreeNode(
                key=str(occ.order),
                title=occ.title,
                level=occ.level,
                parent_key=str(parent.order) if parent is not None else None,
                order=occ.order,
                is_chapter=occ.level == 1,
                line=occ.line,
            )
        )
        stack.append(occ)
        content_start = occ.line  # 0 基 index = occ.line（下一行）
        next_line = occs[idx + 1].line if idx + 1 < len(occs) else len(lines) + 1
        content = "\n".join(lines[content_start : next_line - 1])
        path_titles = [o.title for o in stack]
        paras = [
            Para(text=p, line_start=a, line_end=b)
            for p, a, b in split_paragraphs(content, line_offset=content_start)
        ]
        sections.append(
            RawSection(
                node_key=str(occ.order),
                level_path=path_titles,
                title=occ.title,
                content=content,
                paragraphs=paras,
            )
        )
    return nodes, sections


def paragraphs_plain(content: str) -> list[Para]:
    return [
        Para(text=p, line_start=a, line_end=b)
        for p, a, b in split_paragraphs(content, line_offset=0)
    ]
