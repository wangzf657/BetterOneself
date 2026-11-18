"""复习卡片与评分记录(M3-05, M4-02/03/04)。FSRS 记忆状态由 py-fsrs 计算写入。"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TimestampMixin


class Card(TimestampMixin, Base):
    __tablename__ = "cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    study_id: Mapped[int] = mapped_column(
        ForeignKey("studies.id", ondelete="CASCADE"), index=True
    )
    kp_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"), index=True
    )
    front: Mapped[str] = mapped_column(Text)
    back_md: Mapped[str] = mapped_column(Text)
    chunk_id: Mapped[int | None] = mapped_column(ForeignKey("source_chunks.id"))
    # auto_quiz(错题自动)/ manual_mark(对话卡壳标记)/ manual_new(手建)
    origin: Mapped[str] = mapped_column(String(16), default="auto_quiz")
    # active / suspended(M4-04 暂停)
    status: Mapped[str] = mapped_column(String(16), default="active")
    # 到期即查询字段:复习队列按此出队
    due: Mapped[datetime] = mapped_column(DateTime, index=True)
    stability: Mapped[float | None] = mapped_column(Float)
    difficulty: Mapped[float | None] = mapped_column(Float)
    state: Mapped[str | None] = mapped_column(String(16))
    last_review_at: Mapped[datetime | None] = mapped_column(DateTime)


class ReviewLog(Base):
    __tablename__ = "review_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(
        ForeignKey("cards.id", ondelete="CASCADE"), index=True
    )
    # 1 忘了 / 2 困难 / 3 良好 / 4 轻松
    rating: Mapped[int]
    scheduled_days: Mapped[float] = mapped_column(Float, default=0)
    elapsed_days: Mapped[float] = mapped_column(Float, default=0)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
