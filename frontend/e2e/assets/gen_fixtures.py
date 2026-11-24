# ruff: noqa
"""生成 B6-07 E2E 测试夹具：sample.epub（含图）与 sample.pdf（含书签）。

标准库实现，产物为提交进仓库的固定二进制；需要改动内容时重跑：
    backend/.venv/Scripts/python.exe frontend/e2e/assets/gen_fixtures.py
"""

from __future__ import annotations

import struct
import zlib
import zipfile
from pathlib import Path

HERE = Path(__file__).parent


def tiny_png() -> bytes:
    """2x2 纯色 PNG（无外部依赖，zlib+struct 手工拼装）。"""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    ihdr = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)
    # 每行 filter 0 + RGB 像素
    raw = b"\x00" + b"\x10\x60\xc0" * 2 + b"\x00" + b"\x10\x60\xc0" * 2
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


CH1 = """<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="zh" lang="zh">
<head><title>第一章 上下文</title><meta charset="utf-8"/></head>
<body>
<h1 id="c1">第一章 上下文</h1>
<p>上下文窗口并不是越长越好，信息的组织方式决定了模型的注意力分布。</p>
<p>信息筛选的目标是保留与当前任务直接相关的证据，而不是收集得越多越好。</p>
<figure><img src="images/fig1.png" alt="上下文示意图"/><figcaption>图 1：上下文构成示意</figcaption></figure>
</body>
</html>
"""

CH2 = """<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="zh" lang="zh">
<head><title>第二章 检索</title><meta charset="utf-8"/></head>
<body>
<h1 id="c2">第二章 检索</h1>
<p>检索补足的原则是只取与当前问题相关的切片，信噪比优先于覆盖率。</p>
</body>
</html>
"""

NAV = """<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>目录</title><meta charset="utf-8"/></head>
<body>
<nav epub:type="toc" id="toc">
<ol>
<li><a href="ch1.xhtml">第一章 上下文</a></li>
<li><a href="ch2.xhtml">第二章 检索</a></li>
</ol>
</nav>
</body>
</html>
"""

OPF = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="uid">urn:uuid:e2e-sample-book</dc:identifier>
<dc:title>E2E 样例书</dc:title>
<dc:language>zh</dc:language>
</metadata>
<manifest>
<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
<item id="c1" href="ch1.xhtml" media-type="application/xhtml+xml"/>
<item id="c2" href="ch2.xhtml" media-type="application/xhtml+xml"/>
<item id="fig1" href="images/fig1.png" media-type="image/png"/>
</manifest>
<spine>
<itemref idref="c1"/>
<itemref idref="c2"/>
</spine>
</package>
"""

CONTAINER = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""


def build_epub() -> None:
    path = HERE / "sample.epub"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/content.opf", OPF, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/nav.xhtml", NAV, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/ch1.xhtml", CH1, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/ch2.xhtml", CH2, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/images/fig1.png", tiny_png(), compress_type=zipfile.ZIP_STORED)
    print(f"wrote {path} ({path.stat().st_size} bytes)")


def pdf_escape(s: str) -> str:
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def page_content(lines: list[tuple[float, str]]) -> bytes:
    parts = []
    for y, text in lines:
        parts.append(f"BT /F1 {12 if y == 720 else 11} Tf 72 {y} Td ({pdf_escape(text)}) Tj ET")
    return "\n".join(parts).encode("ascii")


def build_pdf() -> None:
    # 3 页：章首页（0）、1.1（1）、1.2（2）；书签即目录（高置信度路径）
    contents = [
        page_content([(720, "Chapter 1 Basics"), (690, "An agent senses the world and acts on it."),
                      (670, "This chapter introduces the basic loop of observe think act.")]),
        page_content([(720, "1.1 Agents"), (690, "The core of an agent is the decision loop."),
                      (670, "Information filtering keeps evidence relevant to the current task.")]),
        page_content([(720, "1.2 Memory"), (690, "Memory decides how much history an agent can use."),
                      (670, "Planning splits a goal into executable steps.")]),
    ]

    header = b"%PDF-1.4\n"
    objs: list[bytes] = []
    # 1 catalog, 2 pages, 3-5 pages, 6-8 contents, 9 font, 10 outlines, 11-14 outline items
    objs.append(b"<< /Type /Catalog /Pages 2 0 R /Outlines 10 0 R >>")
    objs.append(b"<< /Type /Pages /Kids [3 0 R 4 0 R 5 0 R] /Count 3 >>")
    for i in range(3):
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {6 + i} 0 R "
            f"/Resources << /Font << /F1 9 0 R >> >> >>".encode()
        )
    for c in contents:
        objs.append(b"<< /Length " + str(len(c)).encode() + b" >>\nstream\n" + c + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    objs.append(b"<< /Type /Outlines /First 11 0 R /Last 11 0 R /Count 1 >>")
    objs.append(
        b"<< /Title (Chapter 1 Basics) /Parent 10 0 R /Count 2 /First 12 0 R /Last 13 0 R "
        b"/Dest [3 0 R /XYZ null null null] >>"
    )
    objs.append(b"<< /Title (1.1 Agents) /Parent 11 0 R /Next 13 0 R /Dest [4 0 R /XYZ null null null] >>")
    objs.append(b"<< /Title (1.2 Memory) /Parent 11 0 R /Prev 12 0 R /Dest [5 0 R /XYZ null null null] >>")

    out = bytearray(header)
    offsets = [0]
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()

    path = HERE / "sample.pdf"
    path.write_bytes(bytes(out))
    print(f"wrote {path} ({len(out)} bytes)")


if __name__ == "__main__":
    build_epub()
    build_pdf()
