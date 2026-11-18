"""知识库资料、项目关联与切片(M1-02~07, M2-01)。Source 独立于 Study:一次导入多处复用。"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    # pdf / md / url / github / text
    type: Mapped[str] = mapped_column(String(8))
    origin: Mapped[str] = mapped_column(String(1000), default="")
    raw_path: Mapped[str | None] = mapped_column(String(1000))
    content_md: Mapped[str | None] = mapped_column(Text)
    # pending / processing / ready / failed
    parse_status: Mapped[str] = mapped_column(String(16), default="pending")
    parse_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class StudySource(Base):
    __tablename__ = "study_sources"

    study_id: Mapped[int] = mapped_column(
        ForeignKey("studies.id", ondelete="CASCADE"), primary_key=True
    )
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True
    )


class SourceChunk(Base):
    __tablename__ = "source_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int]
    content: Mapped[str] = mapped_column(Text)
    # 如 `4.2 所有权 > 移动语义`,引用展示用
    heading_path: Mapped[str] = mapped_column(String(500), default="")
    # JSON:页码/行号,阅读页定位高亮用(数据模型 3.1)
    location: Mapped[str] = mapped_column(String(200), default="{}")
