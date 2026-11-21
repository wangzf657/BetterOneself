"""上传边界与请求来源校验（P1-06、技术方案 §11）。"""

from __future__ import annotations

import re
import zipfile

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import get_config
from app.core.errors import UnsupportedMedia, Validation

ALLOWED_EXTS = {"pdf", "epub", "txt", "md", "markdown"}
EXT_TO_TYPE = {"pdf": "pdf", "epub": "epub", "txt": "txt", "md": "md", "markdown": "md"}

_PDF_MAGIC = b"%PDF-"
_ZIP_MAGIC = b"PK\x03\x04"


def ext_of(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def sniff_type(filename: str, head: bytes) -> str:
    """扩展名 + 文件签名（magic bytes）双重校验，返回内部类型。"""
    ext = ext_of(filename)
    if ext not in ALLOWED_EXTS:
        raise UnsupportedMedia(f"不支持的文件格式 .{ext or '?'}：仅支持 EPUB、TXT、PDF、Markdown")
    t = EXT_TO_TYPE[ext]
    if t == "pdf" and not head.startswith(_PDF_MAGIC):
        raise UnsupportedMedia("文件内容不是有效的 PDF（签名校验失败）")
    if t == "epub" and not head.startswith(_ZIP_MAGIC):
        raise UnsupportedMedia("文件内容不是有效的 EPUB（签名校验失败）")
    if t in {"txt", "md"}:
        # 文本格式：抽样解码校验（utf-8 / gb18030 / utf-16）
        sample = head[:4096]
        if not _decodable(sample):
            raise UnsupportedMedia("文件内容不是可读文本（编码无法识别）")
    return t


def _decodable(sample: bytes) -> bool:
    for enc in ("utf-8", "gb18030", "utf-16"):
        try:
            sample.decode(enc)
            return True
        except (UnicodeDecodeError, UnicodeError):
            continue
    return False


def safe_stored_name(type_: str) -> str:
    """存储路径服务端生成，文件名只作显示。"""
    import uuid

    return f"{uuid.uuid4().hex}.{type_}"


def check_epub_safety(zf: zipfile.ZipFile) -> None:
    """zip 炸弹与路径穿越防护（我们只读取指定 entry，不解压落盘）。"""
    cfg = get_config()
    infos = zf.infolist()
    if len(infos) > cfg.max_epub_entries:
        raise Validation(f"EPUB 条目数过多（{len(infos)}），已拒绝")
    total = 0
    for info in infos:
        name = info.filename
        if name.startswith(("/", "\\")) or ".." in name or ":" in name:
            raise Validation(f"EPUB 含可疑路径条目：{name[:60]}")
        if info.file_size > 64 * 1024 * 1024:
            raise Validation("EPUB 单个条目解压后过大，已拒绝")
        if info.compress_size > 0 and info.file_size / info.compress_size > 200:
            raise Validation(f"EPUB 条目压缩比异常：{name[:60]}")
        total += info.file_size
        if total > cfg.max_epub_uncompressed:
            raise Validation("EPUB 解压总大小超限，已拒绝")


def sanitize_error(exc: Exception) -> str:
    """内部异常不泄露密钥、文件绝对路径或模型请求头（接口设计 §1）。"""
    msg = str(exc) or exc.__class__.__name__
    msg = re.sub(r"[A-Za-z]:\\[^\s'\"]+", "<路径已隐藏>", msg)
    msg = re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "sk-****", msg)
    msg = re.sub(r"Bearer\s+\S+", "Bearer ****", msg, flags=re.I)
    return msg[:300]


_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})


class OriginCheckMiddleware:
    """默认仅本机监听；校验 Host/Origin，拒绝跨源写请求（防本机其他页面借浏览器写数据）。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
            host = headers.get("host", "").split(":")[0].strip().lower()
            origin = headers.get("origin", "")
            if host and host not in _LOCAL_HOSTS:
                await _plain_response(403, "仅允许本机访问")(scope, receive, send)
                return
            if origin:
                allowed = get_config().allowed_origins()
                if origin not in allowed and origin not in (
                    f"http://{h}" for h in _LOCAL_HOSTS
                ) and not any(origin.startswith(f"http://{h}:") for h in _LOCAL_HOSTS):
                    await _plain_response(403, "拒绝跨源请求")(scope, receive, send)
                    return
        await self.app(scope, receive, send)


def _plain_response(status: int, text: str) -> ASGIApp:
    from starlette.responses import PlainTextResponse

    async def handler(scope: Scope, receive: Receive, send: Send) -> None:
        response = PlainTextResponse(text, status_code=status)
        await response(scope, receive, send)

    return handler


__all__ = [
    "ALLOWED_EXTS",
    "OriginCheckMiddleware",
    "check_epub_safety",
    "ext_of",
    "safe_stored_name",
    "sanitize_error",
    "sniff_type",
]
