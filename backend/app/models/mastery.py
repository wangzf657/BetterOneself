"""掌握状态变更证据链(M6-01)与每日摘要/周复盘(M5-03/05)。"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class MasteryEvent(Base):
    __tablename__ = "mastery_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    kp_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"), index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(16))
    to_status: Mapped[str] = mapped_column(String(16))
    # quiz / review
    evidence_type: Mapped[str] = mapped_column(String(16))
    evidence_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Summary(Base):
    __tablename__ = "summaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    study_id: Mapped[int] = mapped_column(
        ForeignKey("studies.id", ondelete="CASCADE"), index=True
    )
    # daily / weekly
    summary_type: Mapped[str] = mapped_column(String(16))
    period_date: Mapped[date] = mapped_column(Date)
    content_md: Mapped[str] = mapped_column(Text)
    # 指标快照(数据模型第 4 节),防 due 等字段随后续复习漂移
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
