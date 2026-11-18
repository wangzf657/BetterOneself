"""知识点:树、来源引用、依赖边(M2-01/02/03, M6-01/03)。所有模块的枢纽。"""

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TimestampMixin


class KnowledgePoint(TimestampMixin, Base):
    __tablename__ = "knowledge_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    study_id: Mapped[int] = mapped_column(
        ForeignKey("studies.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text, default="")
    # concept / fact / procedure
    kp_type: Mapped[str] = mapped_column(String(16), default="concept")
    # 无来源支撑时 UI 标注"AI 推断"(M2-01)
    ai_inferred: Mapped[bool] = mapped_column(Boolean, default=False)
    # 系统评估快照:new / learning / passed / weak,由证据驱动(M6-01)
    mastery_status: Mapped[str] = mapped_column(String(16), default="new")
    # 用户自评:unknown / mastered,与系统评估分离(M6-03)
    self_reported: Mapped[str] = mapped_column(String(16), default="unknown")
    sort_order: Mapped[int] = mapped_column(default=0)


class KnowledgeRef(Base):
    __tablename__ = "knowledge_refs"

    kp_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"), primary_key=True
    )
    chunk_id: Mapped[int] = mapped_column(
        ForeignKey("source_chunks.id", ondelete="CASCADE"), primary_key=True
    )


class KpDependency(Base):
    __tablename__ = "kp_dependencies"

    kp_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"), primary_key=True
    )
    depends_on_kp_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"), primary_key=True
    )
