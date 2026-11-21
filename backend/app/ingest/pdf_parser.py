"""PDF 解析（决策 #32）：书签优先建结构（原书目录·高置信度），
无书签时降级为编号标题规则识别（标题规则识别·低置信度，P03 状态条提示检查）。
正文按页提取；书签页码区间确定目录归属；完整链路属 §4.3 待验证 spike 范畴。
"""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from app.core.config import get_config
from app.core.errors import Validation
from app.ingest.headings import detect_heading
from app.ingest.textio import normalize_text, split_paragraphs
from app.ingest.types import Para, ParsedBook, RawSection, TreeNode


def _extract_pages(reader: PdfReader) -> list[str]:
    pages: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        pages.append(normalize_text(text))
    return pages


def _walk_outline(
    reader: PdfReader,
    items: list[object],
    level: int,
    parent_key: str | None,
    counter: list[int],
    flat: list[TreeNode],
) -> None:
    last_key: str | None = parent_key
    for item in items:
        if isinstance(item, list):
            if last_key is not None:
                _walk_outline(reader, item, level + 1, last_key, counter, flat)
            continue
        try:
            title = (item.title or "").strip()  # type: ignore[attr-defined]
            page_no = reader.get_destination_page_number(item)  # type: ignore[arg-type]
        except Exception:
            continue
        if not title:
            continue
        counter[0] += 1
        key = str(counter[0])
        flat.append(
            TreeNode(
                key=key,
                title=title,
                level=level,
                parent_key=parent_key,
                order=counter[0],
                is_chapter=level == 1,
                page=page_no,
            )
        )
        last_key = key


def _path_of(by_key: dict[str, TreeNode], node: TreeNode) -> list[str]:
    path: list[str] = []
    cur: TreeNode | None = node
    while cur is not None:
        path.insert(0, cur.title)
        cur = by_key.get(cur.parent_key) if cur.parent_key else None
    return path


def parse_pdf(path: Path) -> ParsedBook:
    try:
        reader = PdfReader(str(path), strict=False)
    except Exception as e:
        raise Validation(f"无法读取 PDF：{e.__class__.__name__}") from e
    if len(reader.pages) > get_config().max_pdf_pages:
        raise Validation(f"PDF 页数超过上限（{get_config().max_pdf_pages} 页）")
    pages = _extract_pages(reader)

    outline: list[object] | None = None
    try:
        outline = reader.outline  # type: ignore[assignment]
    except Exception:
        outline = None

    if outline:
        flat: list[TreeNode] = []
        _walk_outline(reader, outline, 1, None, [0], flat)
        if flat:
            by_key = {n.key: n for n in flat}
            sections: list[RawSection] = []
            for page_idx, page_text in enumerate(pages):
                if not page_text:
                    continue
                # 该页归属：扁平书签顺序中最后一个起始页 ≤ 本页的书签（即当前最深活动书签）
                active: TreeNode | None = None
                for node in flat:
                    if node.page is not None and node.page <= page_idx:
                        active = node
                if active is None:
                    continue  # 首个书签之前的封面/前言等
                sections.append(
                    RawSection(
                        node_key=active.key,
                        level_path=_path_of(by_key, active),
                        title=active.title,
                        content=page_text,
                        page=page_idx,
                        para_kind="pages",
                        paragraphs=None,
                    )
                )
            return ParsedBook(
                source_type="pdf",
                confidence=0.9,
                confidence_basis="原书目录",
                tree_nodes=flat,
                sections=sections,
                total_pages=len(pages),
            )

    return _fallback_by_text(pages)


def _fallback_by_text(pages: list[str]) -> ParsedBook:
    """无书签：全书逐行做标题规则识别；location 用页码区间。"""
    all_lines: list[str] = []
    line_pages: list[int] = []
    for p_idx, text in enumerate(pages):
        for line in text.split("\n"):
            all_lines.append(line)
            line_pages.append(p_idx)

    hits: list[tuple[int, int, str]] = []  # (line_idx, level, title)
    for i, line in enumerate(all_lines):
        hit = detect_heading(line)
        if hit:
            hits.append((i, hit[0], hit[1]))
    if not hits:
        return ParsedBook(
            source_type="pdf",
            confidence=0.3,
            confidence_basis="不确定结构",
            total_pages=len(pages),
        )

    nodes: list[TreeNode] = []
    sections: list[RawSection] = []
    stack: list[tuple[int, str]] = []  # (level, key)
    for idx, (line_idx, level, title) in enumerate(hits):
        while stack and stack[-1][0] >= level:
            stack.pop()
        parent_key = stack[-1][1] if stack else None
        key = str(idx + 1)
        nodes.append(
            TreeNode(
                key=key,
                title=title,
                level=level,
                parent_key=parent_key,
                order=idx + 1,
                is_chapter=level == 1,
                page=line_pages[line_idx],
            )
        )
        stack.append((level, key))
        content_start = line_idx + 1
        content_end = hits[idx + 1][0] if idx + 1 < len(hits) else len(all_lines)
        content = "\n".join(all_lines[content_start:content_end])
        if not content.strip():
            continue
        paras: list[Para] = []
        for p_text, a, b in split_paragraphs(content, line_offset=content_start):
            page_a = line_pages[a - 1] if 0 < a <= len(line_pages) else 0
            page_b = line_pages[min(b, len(line_pages)) - 1] if b >= 1 else page_a
            paras.append(Para(text=p_text, line_start=page_a, line_end=page_b))
        sections.append(
            RawSection(
                node_key=key,
                level_path=[t for _, t in stack],
                title=title,
                content=content,
                paragraphs=paras,
                para_kind="pages",
            )
        )
    return ParsedBook(
        source_type="pdf",
        confidence=0.5,
        confidence_basis="标题规则识别",
        tree_nodes=nodes,
        sections=sections,
        total_pages=len(pages),
    )
