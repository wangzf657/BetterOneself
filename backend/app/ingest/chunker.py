"""切片（技术方案 §4.4）：按标题层级组织，不按整章切。

- 「章-节」是学习单元粒度，切片粒度 ≤ MAX_CHARS（沿用前身实测值量级，检索抽评后可调）；
- location 保存按格式区分的 JSON 联合类型，回跳不依赖标题模糊搜索；
- 段落整块取舍：单个超长段落保持完整（宁可 chunk 略长也不给错误定位）。
"""

from __future__ import annotations

import json

from app.ingest.types import ChunkDraft, ParsedBook, RawSection

MAX_CHARS = 1500


def _chunks_from_paragraphs(
    sec: RawSection, base_loc: dict[str, object], loc_key: tuple[str, str] | None
) -> list[tuple[str, dict[str, object]]]:
    assert sec.paragraphs is not None
    out: list[tuple[str, dict[str, object]]] = []
    buf: list[str] = []
    buf_start: tuple[int, int] | None = None
    buf_end: tuple[int, int] | None = None

    def flush() -> None:
        nonlocal buf, buf_start, buf_end
        if buf:
            text = "\n\n".join(buf)
            if loc_key is not None:
                assert buf_start is not None and buf_end is not None
                # 存标量起止值（buf_* 是 (start, end) span 元组）；location 是前端回跳与原文定位的坐标系
                loc = {**base_loc, loc_key[0]: buf_start[0], loc_key[1]: buf_end[1]}
            else:
                loc = dict(base_loc)
            out.append((text, loc))
        buf, buf_start, buf_end = [], None, None

    for para in sec.paragraphs:
        if not para.text.strip():
            continue
        span = (para.line_start, para.line_end)
        if buf and len("\n\n".join(buf)) + len(para.text) > MAX_CHARS:
            flush()
        if not buf:
            buf_start = span
        buf.append(para.text)
        buf_end = span
    flush()
    return out


def chunk_section(sec: RawSection) -> list[ChunkDraft]:
    if not sec.content.strip():
        return []
    level_path = " / ".join(sec.level_path)
    results: list[tuple[str, dict[str, object]]] = []

    base: dict[str, object]
    if sec.paragraphs is not None and sec.para_kind == "lines":
        base = {"type": "lines"}
        results = _chunks_from_paragraphs(sec, base, ("line_start", "line_end"))
    elif sec.paragraphs is not None and sec.para_kind == "epub":
        base = {"type": "epub", "href": sec.href}
        if sec.anchor:
            base["anchor"] = sec.anchor
        results = _chunks_from_paragraphs(sec, base, None)
    elif sec.paragraphs is not None and sec.para_kind == "pages":
        # PDF 无书签降级：Para 的 line_start/line_end 实际存页码
        base = {"type": "pdf"}
        results = _chunks_from_paragraphs(sec, base, ("page_start", "page_end"))
    elif sec.page is not None:
        # PDF 书签模式：整节共用单页定位
        base = {"type": "pdf", "page_start": sec.page, "page_end": sec.page}
        results = [(sec.content, dict(base))]
    elif sec.href is not None:
        base = {"type": "epub", "href": sec.href}
        if sec.anchor:
            base["anchor"] = sec.anchor
        results = [(sec.content, dict(base))]
    else:
        results = [(sec.content, {"type": "none", "chapter_hint": sec.title})]

    drafts: list[ChunkDraft] = []
    for text, loc in results:
        if not text.strip():
            continue
        drafts.append(
            ChunkDraft(
                node_key=sec.node_key,
                level_path=level_path,
                title=sec.title,
                content=text,
                location=loc,
            )
        )
    return drafts


def chunk_book(book: ParsedBook) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    for sec in book.sections:
        drafts.extend(chunk_section(sec))
    return drafts


def location_json(loc: dict[str, object]) -> str:
    return json.dumps(loc, ensure_ascii=False)
