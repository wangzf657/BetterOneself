"""ingest 统一中间表示：结构（树）与正文（节）解耦产出。

- 树只含结构信号（零 LLM，阶段 A）；
- 节是切片原料（阶段 B），按标题层级组织，location 为按格式区分的 JSON 联合类型（技术方案 §4.4）。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TreeNode:
    key: str
    title: str
    level: int
    parent_key: str | None
    order: int
    is_chapter: bool
    page: int | None = None  # PDF：起始页（供 page_span）
    line: int | None = None  # TXT/MD：起始行


@dataclass
class Para:
    text: str
    line_start: int
    line_end: int


@dataclass
class RawSection:
    node_key: str | None
    level_path: list[str]
    title: str
    content: str
    # 段落列表：para_kind='lines' 时 line_start/line_end 为行号（TXT/MD），
    # ='pages' 时为页码区间（PDF 无书签降级）；None 表示整节共用单一 location（PDF 按页 / EPUB）
    paragraphs: list[Para] | None = None
    para_kind: str = "lines"
    href: str | None = None  # EPUB
    anchor: str | None = None
    page: int | None = None  # PDF 书签模式：该节所在页


@dataclass
class ChunkDraft:
    node_key: str | None
    level_path: str  # " / " 连接的完整标题路径
    title: str
    content: str
    location: dict[str, object]


@dataclass
class ParsedBook:
    source_type: str
    confidence: float
    confidence_basis: str  # 原书目录 / 标题规则识别 / 不确定结构
    tree_nodes: list[TreeNode] = field(default_factory=list)
    sections: list[RawSection] = field(default_factory=list)
    total_pages: int | None = None  # PDF

    @property
    def has_structure(self) -> bool:
        return bool(self.tree_nodes)
