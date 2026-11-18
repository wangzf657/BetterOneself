"""资料 API 契约(M1-02/05/06)。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

SourceKind = Literal["pdf", "md", "url", "github", "text"]
ParseStatus = Literal["pending", "processing", "ready", "failed"]


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    type: SourceKind
    origin: str
    parse_status: ParseStatus
    parse_error: str | None


class ChunkOut(BaseModel):
    id: int
    seq: int
    content: str
    heading_path: str


class SourceDetail(BaseModel):
    """阅读页数据:chunks 顺序渲染即全文,heading_path 构建目录树。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    type: SourceKind
    origin: str
    parse_status: ParseStatus
    parse_error: str | None
    chunks: list[ChunkOut]
    created_at: datetime
