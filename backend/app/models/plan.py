"""计划与任务(M2-04/05/06, M5-02/04)。重排=改 scheduled_date,不换行。"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    study_id: Mapped[int] = mapped_column(
        ForeignKey("studies.id", ondelete="CASCADE"), index=True
    )
    # draft(访谈后草案)/ active / archived(被新计划替代)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    goal_depth: Mapped[str] = mapped_column(Text, default="")
    deadline: Mapped[date | None] = mapped_column(Date)
    daily_minutes: Mapped[int] = mapped_column(default=45)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PlanEvent(Base):
    __tablename__ = "plan_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("plans.id", ondelete="CASCADE"), index=True
    )
    # generated / confirmed / adjusted / rescheduled
    event_type: Mapped[str] = mapped_column(String(24))
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("plans.id", ondelete="CASCADE"), index=True
    )
    study_id: Mapped[int] = mapped_column(
        ForeignKey("studies.id", ondelete="CASCADE"), index=True
    )
    kp_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"), index=True
    )
    # learn / review_weak / feynman / quiz
    task_type: Mapped[str] = mapped_column(String(16))
    scheduled_date: Mapped[date] = mapped_column(Date, index=True)
    estimated_minutes: Mapped[int] = mapped_column(default=30)
    # pending / done / skipped
    status: Mapped[str] = mapped_column(String(16), default="pending")
    origin_task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"))
    # review_weak 任务携带证据(MasteryEvent id)
    weak_evidence_id: Mapped[str | None] = mapped_column(String(64))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
