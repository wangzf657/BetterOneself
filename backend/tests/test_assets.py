"""原文资产端点（B6-07，V0.1.1 技术设计 §8.3/§8.4）：消毒、防穿越、类型白名单、原文件下发。"""

from __future__ import annotations

import base64
import io
import zipfile
from pathlib import Path

import pytest

from app.ingest.textio import normalize_text
from app.models import Source
from app.services.assets import sanitize_xhtml, valid_asset_path
from tests.conftest import BOOK, api_client, get_study, make_book_db

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)
DOC = "OEBPS/Text/ch1.xhtml"
IMAGE = "OEBPS/Images/a b.png"
IMAGE_PATH = "/assets/OEBPS/Images/a%20b.png"
CHAPTER = """<?xml version="1.0"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>文档标题</title><style>p{color:red}</style></head><body>
<h1 id="h1">第一章 基础</h1>
<p id="p1" onclick="steal()" style="color:red">章正文<em>强调</em>。</p>
<script>alert(1)</script><iframe src="https://evil.example"></iframe>
<img src="../Images/a%20b.png" alt="插图" onerror="alert(1)"/>
<img src="../Images/missing.png" alt="缺图"/>
<img src="https://evil.example/x.png" alt="外链"/>
<img src="data:image/svg+xml;base64,AAAA" alt="内嵌"/>
<img src="../../secret.txt" alt="包内非图片"/>
<img src="../../../../etc/passwd" alt="越出 zip"/>
<img src="/OEBPS/Images/a%20b.png" alt="根绝对"/>
<a id="note1" href="https://evil.example">外链文字</a>
<a href="ch2.xhtml#x">内部链接</a>
<p><!-- 注释 -->结束</p>
</body></html>"""
SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">'
    "<script>alert(1)</script><rect onload=\"x()\" width=\"10\"/><a xlink:href=\"javascript:alert(1)\">"
    "<text>t</text></a><image href=\"https://evil.example/y.png\"/><style>@import url(x)</style></svg>"
)
IMMUTABLE = "private, max-age=31536000, immutable"


def _epub() -> bytes:
    nav = """<?xml version="1.0"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body>
<nav epub:type="toc"><ol><li><a href="Text/ch1.xhtml">第一章 基础</a></li></ol></nav></body></html>"""
    opf = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="u">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="u">x</dc:identifier></metadata>
<manifest><item id="n" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
<item id="c1" href="Text/ch1.xhtml" media-type="application/xhtml+xml"/></manifest>
<spine><itemref idref="c1"/></spine></package>"""
    container = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>
<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
</rootfiles></container>"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", container)
        z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/nav.xhtml", nav)
        z.writestr(DOC, CHAPTER)
        z.writestr(IMAGE, PNG)
        z.writestr("OEBPS/Images/fig.svg", SVG)
        z.writestr("OEBPS/Styles/style.css", "p{color:red}")
        z.writestr("secret.txt", "不应被读到")
    return buf.getvalue()


def _binary_book(db, name: str, filename: str, content: bytes) -> int:
    """建二进制格式的书（EPUB / PDF）并解析，返回 source_id。"""
    from app.services import pipeline
    from app.services.studies import create_study

    study, _ = create_study(db, name=name, filename=filename, content=content, idempotency_key=None)
    assert study.primary_source_id is not None
    pipeline.run_parse(study.primary_source_id, start_precheck=False)
    db.expire_all()
    return study.primary_source_id


def _base(source_id: int) -> str:
    return f"/api/sources/{source_id}"


@pytest.fixture
def epub(db) -> int:
    return _binary_book(db, "图解 EPUB", "b.epub", _epub())


def test_spa_cache_headers() -> None:
    """入口页 no-cache（升级立刻生效，不吞发布）；哈希资产 immutable。"""
    from app.core.config import BACKEND_DIR

    dist = BACKEND_DIR.parent / "frontend" / "dist"
    if not (dist / "index.html").is_file():
        return  # 前端未构建的环境（纯后端 CI）跳过
    with api_client() as c:
        r = c.get("/")
        assert r.status_code == 200
        assert r.headers["cache-control"] == "no-cache"
        js = sorted((dist / "assets").glob("index-*.js"))
        if js:
            r2 = c.get(f"/assets/{js[-1].name}")
            assert "immutable" in r2.headers["cache-control"]


def test_sanitize_decodes_content_doc_encodings() -> None:
    """无 XML 声明的 UTF-8 文档曾被他拉丁化（libxml2 不认 <meta charset>）；BOM/UTF-16/声明编码也要认。"""
    utf8 = "<html><body><p>中文段落保留</p></body></html>".encode()
    assert "中文段落保留" in sanitize_xhtml(utf8, 1, "x.xhtml", set())
    utf16 = "<html><body><p>宽编码保留</p></body></html>".encode("utf-16")
    assert "宽编码保留" in sanitize_xhtml(utf16, 1, "x.xhtml", set())
    declared = (
        '<?xml version="1.0" encoding="gb2312"?><html><body><p>声明编码保留</p></body></html>'
    ).encode("gb2312")
    assert "声明编码保留" in sanitize_xhtml(declared, 1, "x.xhtml", set())


def test_xhtml_asset_is_sanitized(epub) -> None:
    """XHTML：白名单消毒、图片改写到资产端点、外链/越界/内嵌图丢弃、保留 id（§8.3）。"""
    with api_client() as c:
        r = c.get(f"{_base(epub)}/assets/{DOC}")
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
        assert r.headers["x-content-type-options"] == "nosniff"
        assert "max-age" in r.headers["cache-control"]
    html = r.text

    assert '<h1 id="h1">第一章 基础</h1>' in html
    assert '<p id="p1">章正文<em>强调</em>。</p>' in html
    assert html.count(f'src="/api/sources/{epub}{IMAGE_PATH}"') == 2  # 相对路径与根绝对路径都解析到同一张图
    assert 'alt="缺图"' in html and "missing.png" not in html
    assert '<a id="note1">外链文字</a>' in html and "内部链接" in html  # 文字保留，只摘链接
    assert 'alt="包内非图片"' in html and 'alt="越出 zip"' in html  # 非图片与越出 zip 的条目都丢弃
    for gone in (
        "alert(", "<script", "<iframe", "<style", "color:red", "文档标题", "<!--", "注释",
        "evil.example", "data:", "secret.txt", "passwd", "ch2.xhtml", "onclick", "onerror", "href=",
    ):
        assert gone not in html, gone


def test_image_assets_whitelist_and_cache(epub) -> None:
    """图片白名单与 svg 剥离；白名单外类型 415；条目缺失 404 而非 500。"""
    with api_client() as c:
        base = _base(epub)
        png = c.get(f"{base}/assets/{IMAGE}")
        assert png.status_code == 200 and png.content == PNG
        assert png.headers["content-type"] == "image/png"
        assert png.headers["cache-control"] == IMMUTABLE
        assert png.headers["x-content-type-options"] == "nosniff"

        svg = c.get(f"{base}/assets/OEBPS/Images/fig.svg")
        assert svg.status_code == 200 and svg.headers["content-type"] == "image/svg+xml"
        assert svg.content.startswith(b"<svg") and b"<rect" in svg.content
        for gone in (b"script", b"onload", b"javascript:", b"href", b"image", b"style", b"evil.example"):
            assert gone not in svg.content, gone

        assert c.get(f"{base}/assets/OEBPS/Styles/style.css").status_code == 415
        assert c.get(f"{base}/assets/secret.txt").status_code == 415
        assert c.get(f"{base}/assets/OEBPS/Images/missing.png").status_code == 404
        assert c.get(f"{base}/assets/nothing.xhtml").status_code == 404


def test_asset_path_traversal_rejected(epub) -> None:
    """穿越、绝对路径、盘符、反斜杠、空段、NUL、多重编码：一律 404，读不到 zip 外的文件。"""
    with api_client() as c:
        base = f"{_base(epub)}/assets"
        for raw in (
            "..%2F..%2Fsecret.txt",
            "%2e%2e/secret.txt",
            "..%2F..%2F..%2FWindows%2Fwin.ini",
            "C:%5CWindows%2Fwin.ini",
            "%2Fetc%2Fpasswd",
            "OEBPS%2F%2FText%2Fch1.xhtml",
            "OEBPS/.%2FText%2Fch1.xhtml",
            "OEBPS%5CText%5Cch1.xhtml",
            f"{DOC}%00",
            "%252e%252e%2Fsecret.txt",
        ):
            r = c.get(f"{base}/{raw}")
            assert r.status_code == 404, (raw, r.status_code, r.text[:200])
        assert c.get(f"{base}/{DOC}").status_code == 200  # 合法路径不受影响

    # 端点收到的是解码后的路径：校验函数本身对各种越界形态都要拒绝
    valid = valid_asset_path
    assert valid(DOC) and valid(IMAGE)
    for bad in ("", ".", "..", "../a", "a/../b", "/a", "C:/a", "a\\b", "a//b", "a/./b", "a\x00b", "a:b"):
        assert not valid(bad), bad


def test_assets_only_for_epub_and_missing_file(db, epub) -> None:
    txt = make_book_db(db, name="文本书").primary_source_id
    db.expire_all()
    with api_client() as c:
        assert c.get(f"{_base(txt)}/assets/x.png").status_code == 404
        assert c.get("/api/sources/9999/assets/x.png").status_code == 404

        Path(db.get(Source, epub).stored_path).unlink()
        assert c.get(f"{_base(epub)}/assets/{DOC}").status_code == 404  # 原文件缺失：404 而非 500

        Path(db.get(Source, txt).stored_path).unlink()
        assert c.get(f"{_base(txt)}/original").status_code == 404


def test_node_content_names_its_source(db) -> None:
    """节点内容带上主文件 id 与格式：原文视图据此取原文件或资产（B6-07）。"""
    txt = make_book_db(db, name="文本书").primary_source_id
    db.expire_all()
    with api_client() as c:
        tree = c.get(f"/api/studies/{get_study(db).id}/knowledge").json()

        def walk(nodes):
            for n in nodes:
                yield n
                yield from walk(n["children"])

        unit = next(n for n in walk(tree["nodes"]) if n["is_learning_unit"])
        content = c.get(f"/api/kps/{unit['id']}/content").json()
        assert content["source_id"] == txt and content["source_type"] == "txt"


def test_original_text_is_normalized(db) -> None:
    """TXT / MD 下发规范化文本（行号才与 location 一致）；EPUB 没有可下发的原文文件。"""
    txt = make_book_db(db, name="文本书").primary_source_id
    md = make_book_db(
        db, name="Markdown 书", content="# 标题\r\n\r\n正文  \r\n\r\n第二节\r\n", filename="b.md"
    ).primary_source_id
    with api_client() as c:
        r = c.get(f"{_base(txt)}/original")
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
        assert r.text == normalize_text(BOOK)
        assert r.headers["cache-control"] == IMMUTABLE

        r = c.get(f"{_base(md)}/original")
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/markdown")
        assert r.text == "# 标题\n\n正文\n\n第二节"

    epub = _binary_book(db, "图解 EPUB", "b.epub", _epub())
    with api_client() as c:
        assert c.get(f"{_base(epub)}/original").status_code == 415


def test_original_pdf_supports_range(db) -> None:
    pypdf = pytest.importorskip("pypdf")
    buf = io.BytesIO()
    w = pypdf.PdfWriter()
    for _ in range(3):
        w.add_blank_page(width=500, height=700)
    w.write(buf)
    data = buf.getvalue()
    base = _base(_binary_book(db, "PDF 书", "b.pdf", data))
    with api_client() as c:
        r = c.get(f"{base}/original")
        assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
        assert r.content == data and r.headers["accept-ranges"] == "bytes"
        part = c.get(f"{base}/original", headers={"Range": "bytes=0-9"})
        assert part.status_code == 206 and part.content == data[:10]
        assert part.headers["content-range"] == f"bytes 0-9/{len(data)}"
