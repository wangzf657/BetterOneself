"""原文资产（B6-07，V0.1.1 技术设计 §8.3/§8.4）：EPUB 条目读取与消毒、原文件下发。"""

from __future__ import annotations

import posixpath
import re
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote, unquote, urldefrag

import nh3
from lxml import etree
from lxml import html as lxml_html

from app.core.errors import NotFound, UnsupportedMedia
from app.ingest.textio import normalize_text, read_text_bytes
from app.models import Source

IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}
DOC_SUFFIXES = {".xhtml", ".html", ".htm"}
CACHE_IMMUTABLE = {
    "Cache-Control": "private, max-age=31536000, immutable",
    "X-Content-Type-Options": "nosniff",
}
# 消毒结果取决于代码版本：文档片段只给中等缓存；图片对应原文件版本，可长缓存
CACHE_DOCUMENT = {"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"}

# EPUB 属外部输入：只放行排版所需标签；id 留给锚点定位，a 不放行 href
ALLOWED_TAGS = {
    "a", "abbr", "address", "article", "aside", "b", "bdi", "bdo", "blockquote", "br", "caption",
    "cite", "code", "col", "colgroup", "dd", "del", "details", "dfn", "div", "dl", "dt", "em",
    "figcaption", "figure", "footer", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "i",
    "img", "ins", "kbd", "li", "main", "mark", "nav", "ol", "p", "pre", "q", "rp", "rt", "ruby",
    "s", "samp", "section", "small", "span", "strike", "strong", "sub", "summary", "sup", "table",
    "tbody", "td", "tfoot", "th", "thead", "time", "tr", "u", "ul", "var", "wbr",
}
ALLOWED_ATTRIBUTES = {
    "*": {"id"},
    "img": {"src", "alt", "width", "height"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
}
_SVG_STRIP_ELEMENTS = {
    "script", "style", "foreignobject", "iframe", "object", "embed", "image", "audio", "video",
}
_SVG_STRIP_ATTRS = {"href", "style", "src", "action", "formaction"}


def valid_asset_path(path: str) -> bool:
    """zip 内规范化相对路径：拒绝 `..`、绝对路径、盘符、反斜杠、空段、NUL。"""
    if not path or path.startswith("/") or any(c in path for c in ("\\", ":", "\x00")):
        return False
    return all(part not in ("", ".", "..") for part in path.split("/"))


def asset_url(source_id: int, name: str) -> str:
    return f"/api/sources/{source_id}/assets/{quote(name, safe='/')}"


def _suffix(name: str) -> str:
    _, dot, ext = name.rpartition(".")
    return f".{ext.lower()}" if dot and "/" not in ext else ""


def _in_zip(names: set[str], doc_href: str, src: str) -> str | None:
    """把 XHTML 里的图片地址解析成 zip 内图片条目；越出 zip、外链、非图片或不存在返回 None。"""
    url = urldefrag(src.strip())[0].split("?", 1)[0]
    if not url:
        return None
    base = "" if url.startswith("/") else posixpath.dirname(doc_href)
    name = posixpath.normpath(posixpath.join(base, unquote(url.lstrip("/"))))
    suffix = _suffix(name)
    if not valid_asset_path(name) or name not in names:
        return None
    return name if suffix == ".svg" or suffix in IMAGE_TYPES else None


_XML_ENC = re.compile(rb'^\s*<\?xml[^>]*encoding=["\']([\w-]+)["\']')


def _decode_doc(raw: bytes) -> str:
    """EPUB 内容文档按规范为 UTF-8/UTF-16；先按 BOM 与 XML 声明解码再交给解析器，
    不能让 HTML 解析器对 bytes 自行探测（libxml2 不认 <meta charset>，会错读成 Latin-1）。"""
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    m = _XML_ENC.match(raw)
    if m:
        try:
            text = raw.decode(m.group(1).decode("ascii"))
        except (LookupError, UnicodeDecodeError):
            pass
        else:
            # 编码声明已消费；lxml 拒收带 encoding 声明的 str，摘掉声明（声明必为 ASCII，字节偏移即字符偏移）
            decl_end = raw.find(b"?>")
            return text[decl_end + 2 :].lstrip() if decl_end != -1 else text
    return raw.decode("utf-8", errors="replace")


def _body_fragment(raw: bytes) -> str:
    """取 body 内部 HTML：整篇交给消毒器会把 <title> 等头部文字漏进正文。"""
    try:
        doc = lxml_html.fromstring(_decode_doc(raw))
    except etree.ParserError:
        return ""
    body = doc if doc.tag == "body" else doc.find(".//body")
    if body is None:
        body = doc
    return (body.text or "") + "".join(
        etree.tostring(child, method="html", encoding="unicode") for child in body
    )


def sanitize_xhtml(raw: bytes, source_id: int, doc_href: str, names: set[str]) -> str:
    """返回消毒后的 body 片段：图片改写到资产端点，其余 URL 一律不放行。"""

    def rewrite(tag: str, attr: str, value: str) -> str | None:
        if tag == "img" and attr == "src":
            name = _in_zip(names, doc_href, value)
            return asset_url(source_id, name) if name else None
        return value

    return nh3.clean(
        _body_fragment(raw),
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        attribute_filter=rewrite,
        url_schemes=set(),
        link_rel=None,
    )


def sanitize_svg(raw: bytes) -> bytes:
    """SVG 剥离脚本、事件属性、外链与内嵌资源；解析不了按不支持处理。"""
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    try:
        root = etree.fromstring(raw, parser=parser)
    except etree.XMLSyntaxError as e:
        raise UnsupportedMedia("SVG 无法解析") from e
    for node in list(root.iter(etree.Comment, etree.ProcessingInstruction)):
        node.getparent().remove(node)
    for el in list(root.iter()):
        tag = etree.QName(el).localname.lower()
        if tag in _SVG_STRIP_ELEMENTS and el.getparent() is not None:
            el.getparent().remove(el)
            continue
        for attr in list(el.attrib):
            name = attr.rsplit("}", 1)[-1].lower()
            value = el.attrib[attr]
            if name.startswith("on") or name in _SVG_STRIP_ATTRS or "javascript:" in value.lower():
                del el.attrib[attr]
    clean: bytes = etree.tostring(root)
    return clean


@contextmanager
def _open_zip(source: Source) -> Iterator[zipfile.ZipFile]:
    try:
        with zipfile.ZipFile(source.stored_path) as zf:
            yield zf
    except (OSError, zipfile.BadZipFile) as e:
        raise NotFound("原文件不存在或无法读取") from e


def read_asset(source: Source, asset_path: str) -> tuple[bytes, str, dict[str, str]]:
    """读取 EPUB 条目：XHTML 返回消毒片段，图片按白名单；路径非法或条目缺失一律 404。"""
    if source.type != "epub" or not valid_asset_path(asset_path):
        raise NotFound("资源不存在")
    suffix = _suffix(asset_path)
    with _open_zip(source) as zf:
        names = set(zf.namelist())
        if asset_path not in names:  # 按名字精确匹配，不拼文件系统路径
            raise NotFound("资源不存在")
        if suffix in DOC_SUFFIXES:
            html = sanitize_xhtml(zf.read(asset_path), source.id, asset_path, names)
            return html.encode("utf-8"), "text/html", CACHE_DOCUMENT
        media_type = "image/svg+xml" if suffix == ".svg" else IMAGE_TYPES.get(suffix)
        if media_type is None:
            raise UnsupportedMedia("不支持的资源类型")
        data = zf.read(asset_path)
    if suffix == ".svg":
        data = sanitize_svg(data)
    return data, media_type, CACHE_IMMUTABLE


def original_path(source: Source) -> Path:
    """PDF 原字节路径（FileResponse 支持 Range）；文件缺失 404。"""
    path = Path(source.stored_path)
    if not path.is_file():
        raise NotFound("原文件不存在")
    return path


def original_text(source: Source) -> tuple[str, str]:
    """TXT / MD 下发规范化文本：与切片同源，行号才对得上 location。"""
    if source.type not in ("txt", "md"):
        raise UnsupportedMedia("该格式没有可下发的原文文本")
    try:
        text = normalize_text(read_text_bytes(Path(source.stored_path).read_bytes()))
    except OSError as e:
        raise NotFound("原文件不存在") from e
    return text, "text/markdown" if source.type == "md" else "text/plain"


__all__ = ["original_path", "original_text", "read_asset", "sanitize_xhtml"]
