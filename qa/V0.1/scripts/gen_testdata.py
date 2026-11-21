# -*- coding: utf-8 -*-
"""QA 测试数据生成：最小合法 PDF 与 EPUB 样书 + 坏文件。只生成 qa/V0.1/testdata 下的文件。"""
import os
import zipfile

TD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "testdata")
TD = os.path.abspath(TD)
os.makedirs(TD, exist_ok=True)


def esc(s: str) -> str:
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def make_pdf(path: str, title: str, sections: list[tuple[str, str]]) -> None:
    """单页多行文本 PDF（WinAnsi 不含中文，改用 UTF-16BE 十六进制 CID 演示不可行——
    为保证可解析性，这里用英文正文+中文标题靠字体缺省替换；Docling 容忍度以实测为准）。"""
    lines = [title] + [f"{h}: {b}" for h, b in sections]
    content_parts = ["BT", "/F1 18 Tf", "60 760 Td", f"({esc(lines[0])}) Tj", "/F1 11 Tf", "0 -28 Td"]
    for ln in lines[1:]:
        content_parts.append(f"({esc(ln)}) Tj")
        content_parts.append("0 -18 Td")
    content_parts.append("ET")
    stream = "\n".join(content_parts).encode("latin-1", "replace")

    objs = []
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    objs.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objs)+1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode()
    with open(path, "wb") as f:
        f.write(bytes(out))
    print("PDF written:", path, os.path.getsize(path), "bytes")


def make_epub(path: str, book_id: str, title: str, chapters: list[tuple[str, str]]) -> None:
    container = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""
    nav_items = "\n".join(
        f'<navPoint id="nav{i+1}" playOrder="{i+1}"><navLabel><text>{h}</text></navLabel>'
        f'<content src="ch{i+1}.xhtml"/></navPoint>'
        for i, (h, _) in enumerate(chapters)
    )
    nav = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>{title}</title></head>
<body><nav epub:type="toc" id="toc"><h1>{title}</h1><ol>{nav_items}</ol></nav></body>
</html>"""
    manifest = "\n".join(
        f'<item id="ch{i+1}" href="ch{i+1}.xhtml" media-type="application/xhtml+xml"/>'
        for i, _ in enumerate(chapters)
    )
    spine = "\n".join(f'<itemref idref="ch{i+1}"/>' for i, _ in enumerate(chapters))
    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">urn:uuid:{book_id}</dc:identifier>
    <dc:title>{title}</dc:title>
    <dc:language>zh</dc:language>
    <meta property="dcterms:modified">2026-01-01T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    {manifest}
  </manifest>
  <spine>{spine}</spine>
</package>"""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container)
        z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/nav.xhtml", nav)
        for i, (h, body) in enumerate(chapters):
            ch = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>{h}</title></head>
<body><h1>{h}</h1><p>{body}</p></body></html>"""
            z.writestr(f"OEBPS/ch{i+1}.xhtml", ch)
    print("EPUB written:", path, os.path.getsize(path), "bytes")


make_pdf(
    os.path.join(TD, "QA书-PDF-03.pdf"),
    "QA Book PDF 03: Prompt Engineering Basics",
    [
        ("Chapter 1 What is a prompt",
         "A prompt is the instruction context that conditions model behavior. Good prompts specify task, audience and constraints."),
        ("Chapter 2 Few-shot examples",
         "Few-shot examples teach format and tone. Quality of examples matters more than quantity."),
        ("Chapter 3 Chain of thought",
         "Asking the model to reason step by step improves multi-step accuracy on many tasks."),
    ],
)

make_epub(
    os.path.join(TD, "QA书-EPUB-04.epub"),
    "qa-epub-04",
    "QA书-EPUB-04 机器学习入门",
    [
        ("第 1 章 监督学习", "监督学习从带标签的数据中学习映射。分类与回归是两大任务形态。损失函数衡量预测与真值的差距，优化器负责最小化它。"),
        ("第 2 章 模型评估", "留出集、交叉验证与指标选择决定结论可信度。过拟合的模型在训练集上表现好而泛化差。"),
        ("第 3 章 特征工程", "特征质量常比模型结构更影响结果。归一化、编码与缺失值处理是基本功。"),
    ],
)

# 坏文件：伪 PDF（实为文本）
with open(os.path.join(TD, "QA书-坏文件-05.pdf"), "w", encoding="utf-8") as f:
    f.write("这不是一个真正的 PDF 文件，只是改了扩展名的纯文本，用来测试解析失败路径。")
print("fake pdf written")

# 空文件
open(os.path.join(TD, "QA书-空文件-06.txt"), "wb").close()
print("empty txt written")
