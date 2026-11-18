"""文件解析适配器:MD 直读,PDF 走 Docling(懒加载,避免拖慢启动)。"""

from dataclasses import dataclass
from pathlib import Path

import httpx  # noqa: F401  (里程碑5 GitHub/网页导入使用,先占位统一入口)


@dataclass
class ParsedDoc:
    content_md: str
    # location 兜底:页码定位待 PDF 深化,先以行号近似
    pages_supported: bool = False


def parse_file(path: Path) -> ParsedDoc:
    suffix = path.suffix.lower()
    if suffix in (".md", ".markdown"):
        return ParsedDoc(content_md=path.read_text(encoding="utf-8", errors="replace"))
    if suffix == ".pdf":
        return _parse_pdf(path)
    raise ValueError(f"不支持的文件类型: {suffix}")


def _parse_pdf(path: Path) -> ParsedDoc:
    # 懒加载:docling 引入 torch,导入成本高
    from docling.document_converter import DocumentConverter

    result = DocumentConverter().convert(path)
    return ParsedDoc(content_md=result.document.export_to_markdown())
