"""EPUB 解析（技术方案 §4.2）：标准库 zipfile + lxml/BeautifulSoup，不新增 ebooklib。

结构信号优先级 nav(EPUB3) → NCX(EPUB2) → 正文标题；正文按 spine 顺序读取 XHTML，
保留 href + 锚点定位；XXE 防护：禁外部实体与网络访问（P1-06）。
"""

from __future__ import annotations

import posixpath
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urldefrag

from bs4 import BeautifulSoup, Tag
from lxml import etree

from app.core.errors import Validation
from app.core.security import check_epub_safety
from app.ingest.textio import split_paragraphs
from app.ingest.types import Para, ParsedBook, RawSection, TreeNode

OPF_NS = "http://www.idpf.org/2007/opf"
CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"
_HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}


def _xml(content: bytes) -> etree._Element:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    return etree.fromstring(content, parser=parser)


def _norm_href(base_dir: str, href: str) -> tuple[str, str | None]:
    href, frag = urldefrag(href.strip())
    full = (
        posixpath.normpath(posixpath.join(base_dir, unquote(href)))
        if base_dir
        else posixpath.normpath(unquote(href))
    )
    return full, (frag or None)


@dataclass
class TocEntry:
    title: str
    href: str
    frag: str | None
    children: list[TocEntry]


@dataclass
class _Block:
    idx: int
    kind: str  # heading / text
    text: str
    level: int  # heading 层级；文本块为 0
    anchor: str | None


def _read_toc(zf: zipfile.ZipFile, opf: etree._Element, base_dir: str) -> list[TocEntry] | None:
    manifest = opf.find(f"{{{OPF_NS}}}manifest")
    spine_el = opf.find(f"{{{OPF_NS}}}spine")
    if manifest is None or spine_el is None:
        return None
    items = {i.get("id"): i for i in manifest.findall(f"{{{OPF_NS}}}item")}

    for item in items.values():  # EPUB3 nav
        props = (item.get("properties") or "").split()
        if "nav" in props:
            href, _ = _norm_href(base_dir, item.get("href") or "")
            try:
                soup = BeautifulSoup(zf.read(href), "lxml")
            except KeyError:
                return None
            nav = soup.find("nav", attrs={"epub:type": "toc"}) or soup.find("nav")
            if nav is None:
                return None
            entries = _parse_nav_list(nav.find("ol"))
            return entries or None

    toc_id = spine_el.get("toc")  # EPUB2 NCX
    ncx_item = items.get(toc_id or "")
    if ncx_item is not None:
        href, _ = _norm_href(base_dir, ncx_item.get("href") or "")
        try:
            ncx = _xml(zf.read(href))
        except KeyError:
            return None
        entries = _parse_ncx(ncx)
        return entries or None
    return None


def _parse_nav_list(ol: Tag | None) -> list[TocEntry]:
    if ol is None:
        return []
    entries: list[TocEntry] = []
    for li in ol.find_all("li", recursive=False):
        link = li.find("a")
        if link is None:
            continue
        title = link.get_text(" ", strip=True)
        href = link.get("href") or ""
        if not title or not href:
            continue
        children = _parse_nav_list(li.find("ol"))
        entries.append(TocEntry(title=title, href=str(href), frag=None, children=children))
    return entries


def _parse_ncx(ncx: etree._Element) -> list[TocEntry]:
    ns = {"n": "http://www.daisy.org/z3986/2005/ncx/"}

    def walk(points: list[etree._Element]) -> list[TocEntry]:
        out: list[TocEntry] = []
        for pt in points:
            label = pt.find("n:navLabel/n:text", ns)
            content = pt.find("n:content", ns)
            if label is None or content is None:
                continue
            title = (label.text or "").strip()
            src = content.get("src") or ""
            if not title or not src:
                continue
            subs = walk(pt.findall("n:navPoint", ns))
            out.append(TocEntry(title=title, href=src, frag=None, children=subs))
        return out

    return walk(ncx.findall("n:navMap/n:navPoint", ns))


def _read_file_blocks(zf: zipfile.ZipFile, href: str) -> list[_Block]:
    try:
        raw = zf.read(href)
    except KeyError:
        return []
    soup = BeautifulSoup(raw, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    body = soup.body or soup
    blocks: list[_Block] = []

    def flush(pending: list[str]) -> None:
        text = normalize_blocks(pending)
        if text:
            blocks.append(_Block(len(blocks), "text", text, 0, None))

    pending: list[str] = []
    for el in body.find_all(recursive=False):
        name = getattr(el, "name", "") or ""
        if not name:
            continue
        if name in _HEADING_TAGS:
            flush(pending)
            pending = []
            blocks.append(
                _Block(
                    len(blocks),
                    "heading",
                    el.get_text(" ", strip=True),
                    _HEADING_TAGS[name],
                    str(el.get("id")) if el.get("id") else None,
                )
            )
        else:
            text = el.get_text("\n", strip=True)
            if text:
                pending.append(text)
    flush(pending)
    return blocks


def normalize_blocks(pending: list[str]) -> str:
    import re as _re

    text = "\n\n".join(pending)
    return _re.sub(r"\n{3,}", "\n\n", text).strip()


def parse_epub(path: Path) -> ParsedBook:
    with zipfile.ZipFile(str(path)) as zf:
        check_epub_safety(zf)
        try:
            container = _xml(zf.read("META-INF/container.xml"))
            opf_path = container.find(
                f"{{{CONTAINER_NS}}}rootfiles/{{{CONTAINER_NS}}}rootfile"
            ).get("full-path")
            opf = _xml(zf.read(opf_path))
        except (KeyError, AttributeError, etree.XMLSyntaxError) as e:
            raise Validation(f"EPUB 结构损坏，无法读取 OPF：{e.__class__.__name__}") from e
        base_dir = posixpath.dirname(opf_path)

        manifest = opf.find(f"{{{OPF_NS}}}manifest")
        spine_el = opf.find(f"{{{OPF_NS}}}spine")
        if manifest is None or spine_el is None:
            raise Validation("EPUB 缺少 manifest/spine")
        items = {i.get("id"): i for i in manifest.findall(f"{{{OPF_NS}}}item")}
        spine: list[str] = []
        for itemref in spine_el.findall(f"{{{OPF_NS}}}itemref"):
            item = items.get(itemref.get("idref"))
            if item is not None:
                href, _frag = _norm_href(base_dir, item.get("href") or "")
                media = item.get("media-type") or ""
                if "html" in media or href.endswith((".xhtml", ".html", ".htm")):
                    spine.append(href)

        toc = _read_toc(zf, opf, base_dir)
        file_blocks = {href: _read_file_blocks(zf, href) for href in spine}
        if toc:
            return _build_from_toc(toc, base_dir, spine, file_blocks)
        return _build_from_headings(spine, file_blocks)


def _build_from_toc(
    toc: list[TocEntry],
    base_dir: str,
    spine: list[str],
    file_blocks: dict[str, list[_Block]],
) -> ParsedBook:
    spine_index = {href: i for i, href in enumerate(spine)}

    # 1) 拍平 TOC，计算每个条目的 (spine_idx, block_pos) 文档位置
    flat: list[dict[str, object]] = []

    def walk(entries: list[TocEntry], depth: int, parent_key: str | None) -> None:
        for e in entries:
            key = str(len(flat) + 1)
            href, frag = _norm_href(base_dir, e.href)
            s_idx = spine_index.get(href, -1)
            blocks = file_blocks.get(href, [])
            pos = 0
            if frag:
                for b in blocks:
                    if b.anchor == frag:
                        pos = b.idx
                        break
            flat.append(
                {
                    "key": key,
                    "title": re.sub(r"\s+", " ", e.title).strip(),
                    "parent": parent_key,
                    "depth": depth,
                    "s_idx": s_idx,
                    "pos": pos if s_idx >= 0 else 0,
                }
            )
            walk(e.children, depth + 1, key)

    walk(toc, 1, None)

    nodes = [
        TreeNode(
            key=str(f["key"]),
            title=str(f["title"]),
            level=int(str(f["depth"])),
            parent_key=f["parent"] if isinstance(f["parent"], str) else None,
            order=int(str(f["key"])),
            is_chapter=int(str(f["depth"])) == 1,
        )
        for f in flat
    ]
    by_key = {n.key: n for n in nodes}
    doc_positions = [(int(str(f["s_idx"])), int(str(f["pos"])), str(f["key"])) for f in flat]

    # 2) 每个 block 归属文档序中最后一个位置 ≤ 其位置的目录条目
    sections: list[RawSection] = []
    for s_idx, href in enumerate(spine):
        for block in file_blocks[href]:
            if not block.text.strip():
                continue
            target: str | None = None
            for e_s, e_p, e_key in doc_positions:
                if e_s < 0:
                    continue
                if (e_s, e_p) <= (s_idx, block.idx):
                    target = e_key
            if target is None:
                continue
            node = by_key[target]
            sections.append(
                RawSection(
                    node_key=target,
                    level_path=_level_path(by_key, node),
                    title=node.title,
                    content=block.text,
                    paragraphs=_plain_paras(block.text),
                    para_kind="epub",
                    href=href,
                    anchor=block.anchor if block.kind == "heading" else None,
                )
            )

    return ParsedBook(
        source_type="epub",
        confidence=0.95,
        confidence_basis="原书目录",
        tree_nodes=nodes,
        sections=sections,
    )


def _level_path(by_key: dict[str, TreeNode], node: TreeNode) -> list[str]:
    path: list[str] = []
    cur: TreeNode | None = node
    while cur is not None:
        path.insert(0, cur.title)
        cur = by_key.get(cur.parent_key) if cur.parent_key else None
    return path


def _plain_paras(content: str) -> list[Para]:
    return [
        Para(text=p, line_start=a, line_end=b)
        for p, a, b in split_paragraphs(content, line_offset=0)
    ]


def _build_from_headings(
    spine: list[str], file_blocks: dict[str, list[_Block]]
) -> ParsedBook:
    """nav/NCX 均缺失：用正文 h1–h6 建树（低置信度，标题规则识别）。"""
    nodes: list[TreeNode] = []
    sections: list[RawSection] = []
    stack: list[tuple[int, str]] = []
    order = 0
    for href in spine:
        for block in file_blocks[href]:
            if block.kind == "heading" and block.text.strip():
                while stack and stack[-1][0] >= block.level:
                    stack.pop()
                order += 1
                key = str(order)
                parent = stack[-1][1] if stack else None
                nodes.append(
                    TreeNode(
                        key=key,
                        title=block.text[:120],
                        level=block.level,
                        parent_key=parent,
                        order=order,
                        is_chapter=block.level == 1,
                    )
                )
                stack.append((block.level, key))
            elif block.text.strip() and stack:
                key = stack[-1][1]
                node = by_key_of(nodes, key)
                by_key = {n.key: n for n in nodes}
                sections.append(
                    RawSection(
                        node_key=key,
                        level_path=_level_path(by_key, node),
                        title=node.title,
                        content=block.text,
                        paragraphs=_plain_paras(block.text),
                        para_kind="epub",
                        href=href,
                        anchor=block.anchor,
                    )
                )
    return ParsedBook(
        source_type="epub",
        confidence=0.6 if nodes else 0.3,
        confidence_basis="标题规则识别" if nodes else "不确定结构",
        tree_nodes=nodes,
        sections=sections,
    )


def by_key_of(nodes: list[TreeNode], key: str) -> TreeNode:
    return next(n for n in nodes if n.key == key)
