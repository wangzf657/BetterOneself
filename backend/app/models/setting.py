"""全局:设置单行(M7-01, key 加密)与按天×场景用量(M7-04)。"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Setting(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    llm_base_url: Mapped[str] = mapped_column(String(500), default="")
    llm_api_key_enc: Mapped[str | None] = mapped_column(Text)
    llm_model: Mapped[str] = mapped_column(String(100), default="")
    embed_base_url: Mapped[str] = mapped_column(String(500), default="")
    embed_api_key_enc: Mapped[str | None] = mapped_column(Text)
    embed_model: Mapped[str] = mapped_column(String(100), default="")
    fsrs_params_json: Mapped[str | None] = mapped_column(Text)
    daily_review_limit: Mapped[int] = mapped_column(default=20)
    inactivity_threshold_days: Mapped[int] = mapped_column(default=5)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class UsageDay(Base):
    __tablename__ = "usage_days"
    __table_args__ = (UniqueConstraint("date", "scene", name="uq_usage_date_scene"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    # decompose / chat / quiz / embed
    scene: Mapped[str] = mapped_column(String(16))
    prompt_tokens: Mapped[int] = mapped_column(default=0)
    completion_tokens: Mapped[int] = mapped_column(default=0)
    requests: Mapped[int] = mapped_column(default=0)
    cost_est: Mapped[float] = mapped_column(Float, default=0.0)
