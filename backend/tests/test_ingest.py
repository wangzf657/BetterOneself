"""ingest 单测（技术方案 §12.1）：四格式、跳级、无目录、编码、location 联合类型、安全边界。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.errors import UnsupportedMedia, Validation
from app.core.security import check_epub_safety, sniff_type
from app.ingest import parse_file
from app.ingest.chunker import chunk_book


def _write(tmp_path: Path, name: str, data: bytes | str) -> Path:
    p = tmp_path / name
    p.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    return p


def test_md_full_heading_path_and_lines(tmp_path: Path) -> None:
    md = (
        "# 一 总览\n\n总览正文。\n\n## 1.1 背景\n\n背景正文第一段。\n\n背景正文第二段。\n\n"
        "### 1.1.1 细节\n\n细节正文。\n\n#### 深层\n\n深层内容。\n\n"
        "##### 更深\n\n内容。\n\n###### 最深\n\n内容。\n"
    )
    book = parse_file(_write(tmp_path, "b.md", md), "md")
    levels = [(n.title, n.level, n.parent_key) for n in book.tree_nodes]
    assert ("一 总览", 1, None) in levels
    assert ("1.1.1 细节", 3, "2") in levels  # h1–h6 完整路径，跳级直接嵌套
    assert len(book.tree_nodes) == 6  # h1–h6 全保留
    drafts = chunk_book(book)
    locs = [d.location for d in drafts]
    assert all(
        loc["type"] == "lines"
        and isinstance(loc["line_start"], int)
        and isinstance(loc["line_end"], int)
        and loc["line_start"] <= loc["line_end"]
        for loc in locs
    )  # 标量行号是回跳与原文定位的坐标系（B6-07；曾误存 span 元组）
    # 标题层级路径写入 level_path
    deep = next(d for d in drafts if d.title == "1.1 背景")
    assert "一 总览" in deep.level_path and "1.1 背景" in deep.level_path


def test_txt_zh_chapter_and_numbering(tmp_path: Path) -> None:
    txt = "第一章 导论\n\n章正文。\n\n1.1 小节\n\n节正文。\n\n1.2 另一节\n\n正文。\n\n第二章 实战\n\n正文。\n"
    book = parse_file(_write(tmp_path, "b.txt", txt), "txt")
    titles = [(n.title, n.level, n.is_chapter) for n in book.tree_nodes]
    assert ("第一章 导论", 1, True) in titles
    assert ("1.1 小节", 2, False) in titles
    assert book.confidence_basis == "标题规则识别"


def test_txt_no_structure(tmp_path: Path) -> None:
    txt = "只是普通段落，没有任何标题结构。\n\n第二段也很普通。\n"
    book = parse_file(_write(tmp_path, "b.txt", txt), "txt")
    assert not book.has_structure
    assert book.confidence_basis == "不确定结构"


def test_txt_gb18030_encoding(tmp_path: Path) -> None:
    txt = "第一章 导论\n\n中文内容编码测试。\n"
    p = tmp_path / "b.txt"
    p.write_bytes(txt.encode("gb18030"))
    book = parse_file(p, "txt")
    assert book.tree_nodes and book.tree_nodes[0].title == "第一章 导论"


def test_txt_year_not_heading(tmp_path: Path) -> None:
    txt = "2024 年是关键一年。\n\n正文开始。\n"
    book = parse_file(_write(tmp_path, "b.txt", txt), "txt")
    assert not book.has_structure


def test_pdf_bookmarks_and_pages(tmp_path: Path) -> None:
    pytest.importorskip("pypdf")
    from pypdf import PdfWriter

    w = PdfWriter()
    for _ in range(6):
        w.add_blank_page(width=500, height=700)
    # 手工页无法生成文本；书签结构仍可验证（文本为空 → chunk 无、结构在）
    ch1 = w.add_outline_item("第一章 基础", 1)
    w.add_outline_item("1.1 概念", 2, parent=ch1)
    w.add_outline_item("第二章 进阶", 4)
    p = tmp_path / "b.pdf"
    with open(p, "wb") as f:
        w.write(f)
    book = parse_file(p, "pdf")
    assert book.confidence_basis == "原书目录"
    titles = [(n.title, n.is_chapter, n.page) for n in book.tree_nodes]
    assert ("第一章 基础", True, 1) in titles
    assert ("1.1 概念", False, 2) in titles


def test_epub_nav_structure_and_href(tmp_path: Path) -> None:
    import zipfile

    xhtml_ch1 = """<?xml version="1.0"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>c1</title></head><body>
<h1 id="h1">第一章 基础</h1><p>章正文一。</p>
<h2 id="s11">1.1 概念</h2><p>节正文一。</p></body></html>"""
    xhtml_ch2 = """<?xml version="1.0"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>c2</title></head><body>
<h1 id="h2">第二章 进阶</h1><p>章正文二。</p></body></html>"""
    nav = """<?xml version="1.0"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>nav</title></head><body>
<nav epub:type="toc"><ol>
<li><a href="ch1.xhtml">第一章 基础</a><ol><li><a href="ch1.xhtml#s11">1.1 概念</a></li></ol></li>
<li><a href="ch2.xhtml">第二章 进阶</a></li>
</ol></nav></body></html>"""
    opf = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="u">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="u">x</dc:identifier>
<dc:title>T</dc:title></metadata>
<manifest><item id="n" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
<item id="c1" href="ch1.xhtml" media-type="application/xhtml+xml"/>
<item id="c2" href="ch2.xhtml" media-type="application/xhtml+xml"/></manifest>
<spine><itemref idref="c1"/><itemref idref="c2"/></spine></package>"""
    container = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>"""
    p = tmp_path / "b.epub"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("META-INF/container.xml", container)
        z.writestr("content.opf", opf)
        z.writestr("nav.xhtml", nav)
        z.writestr("ch1.xhtml", xhtml_ch1)
        z.writestr("ch2.xhtml", xhtml_ch2)
    book = parse_file(p, "epub")
    assert book.confidence_basis == "原书目录"
    titles = [(n.title, n.level) for n in book.tree_nodes]
    assert ("第一章 基础", 1) in titles and ("1.1 概念", 2) in titles
    drafts = chunk_book(book)
    sec = [d for d in drafts if d.title == "1.1 概念"]
    assert sec and sec[0].location["type"] == "epub"
    assert sec[0].location["href"] == "ch1.xhtml" and sec[0].location.get("anchor") == "s11"


def test_upload_signature_forgery() -> None:
    with pytest.raises(UnsupportedMedia):
        sniff_type("fake.pdf", b"Not a pdf at all....")  # type: ignore[arg-type]
    with pytest.raises(UnsupportedMedia):
        sniff_type("fake.epub", b"plain text here..")  # type: ignore[arg-type]
    with pytest.raises(UnsupportedMedia):
        sniff_type("evil.exe", b"MZ\x90\x00")  # type: ignore[arg-type]


def test_zip_bomb_rejected(tmp_path: Path) -> None:
    import zipfile

    from app.core.config import get_config

    p = tmp_path / "bomb.epub"
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("a.xhtml", "x" * (get_config().max_epub_uncompressed + 1))
    with zipfile.ZipFile(p) as z, pytest.raises(Validation):
        check_epub_safety(z)
