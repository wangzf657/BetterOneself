"""SQLAlchemy 2 模型：13 张表（数据模型 §3）。

知识点是数据枢纽：会话、测验、笔记、点亮全部通过 kp_id 关联。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    # 保留微秒：updated_at 是规划冲突比对依据，截断会让同秒内的用户编辑不可见
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Study(Base):
    __tablename__ = "studies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    primary_source_id: Mapped[int | None] = mapped_column(
        ForeignKey("sources.id", use_alter=True, ondelete="SET NULL"), unique=True
    )
    scheme: Mapped[str] = mapped_column(String(16), default="guided", server_default="guided")
    outline_status: Mapped[str] = mapped_column(
        String(16), default="idle", server_default="idle"
    )
    outline_error: Mapped[str | None] = mapped_column(Text)
    outline_thesis: Mapped[str | None] = mapped_column(Text)
    last_kp_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_points.id", use_alter=True, ondelete="SET NULL")
    )
    last_learned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    source = relationship("Source", foreign_keys=[primary_source_id], uselist=False)


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(8))  # epub / txt / pdf / md
    filename: Mapped[str] = mapped_column(Text)  # 原始文件名，仅显示
    stored_path: Mapped[str] = mapped_column(Text)  # 服务端生成
    size_bytes: Mapped[int] = mapped_column(Integer)
    parse_status: Mapped[str] = mapped_column(
        String(16), default="pending", server_default="pending"
    )  # pending / parsing / parsed / failed
    parse_error: Mapped[str | None] = mapped_column(Text)
    embed_status: Mapped[str] = mapped_column(
        String(16), default="pending", server_default="pending"
    )  # pending / running / ready / degraded / failed
    embed_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    study = relationship("Study", foreign_keys=[study_id])
    chunks = relationship(
        "SourceChunk", back_populates="source", cascade="all, delete-orphan"
    )


class SourceChunk(Base):
    __tablename__ = "source_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer)
    level_path: Mapped[str] = mapped_column(Text)  # h1–h6 完整标题路径
    title: Mapped[str] = mapped_column(Text)  # 最近一级标题
    content: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(Text)  # JSON 联合类型（按格式区分）
    char_count: Mapped[int] = mapped_column(Integer)

    source = relationship("Source", back_populates="chunks")


class KnowledgePoint(Base):
    __tablename__ = "knowledge_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    study_id: Mapped[int] = mapped_column(
        ForeignKey("studies.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer)
    is_chapter: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))
    origin: Mapped[str] = mapped_column(
        String(16), default="toc", server_default="toc"
    )  # toc / heading / ai_split / ai_merge / ai_organize / ai_group / manual
    confidence: Mapped[float] = mapped_column(Float)
    confidence_basis: Mapped[str] = mapped_column(String(32))
    excluded: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))
    exclusion_reason: Mapped[str | None] = mapped_column(Text)
    planning_note: Mapped[str | None] = mapped_column(Text)
    chapter_summary: Mapped[str | None] = mapped_column(Text)  # 仅 is_chapter=1 有值
    lighted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lighted_by_quiz_id: Mapped[int | None] = mapped_column(
        ForeignKey("quizzes.id", use_alter=True, ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # updated_at 仅用户编辑触发（AI 写 chapter_summary / planning_note 不触发）——规划冲突比对依据
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class KnowledgeRef(Base):
    __tablename__ = "knowledge_refs"
    __table_args__ = (UniqueConstraint("kp_id", "chunk_id", name="uq_refs_kp_chunk"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kp_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[int] = mapped_column(
        ForeignKey("source_chunks.id", ondelete="RESTRICT")
    )
    sort_order: Mapped[int] = mapped_column(Integer)


class OutlineEvent(Base):
    __tablename__ = "outline_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    study_id: Mapped[int] = mapped_column(
        ForeignKey("studies.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(32))
    actor: Mapped[str] = mapped_column(String(8))  # structure / ai / user / system
    kp_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="SET NULL")
    )
    detail_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class Session_(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    study_id: Mapped[int] = mapped_column(
        ForeignKey("studies.id", ondelete="CASCADE"), index=True
    )
    kp_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"), unique=True
    )
    scheme: Mapped[str] = mapped_column(String(16), default="guided", server_default="guided")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # user / assistant
    content: Mapped[str] = mapped_column(Text)  # Markdown
    refs_json: Mapped[str | None] = mapped_column(Text)
    stopped: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class Quiz(Base):
    __tablename__ = "quizzes"
    __table_args__ = (
        # 同一节点同时最多一组进行中的测验（P1-03）
        Index(
            "uq_quizzes_open_kp",
            "kp_id",
            unique=True,
            sqlite_where=text("answered_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    study_id: Mapped[int] = mapped_column(
        ForeignKey("studies.id", ondelete="CASCADE"), index=True
    )
    kp_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    questions_json: Mapped[str] = mapped_column(Text)  # 下发面，不含答案
    answers_json: Mapped[str] = mapped_column(Text)  # 服务端持有：答案、解析、来源 refs
    pass_line: Mapped[int] = mapped_column(Integer)
    submitted_answers_json: Mapped[str | None] = mapped_column(Text)
    grading_results_json: Mapped[str | None] = mapped_column(Text)
    correct_count: Mapped[int | None] = mapped_column(Integer)
    passed: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Note(Base):
    __tablename__ = "notes"
    __table_args__ = (UniqueConstraint("kp_id", name="uq_notes_kp"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    study_id: Mapped[int] = mapped_column(
        ForeignKey("studies.id", ondelete="CASCADE"), index=True
    )
    kp_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id", ondelete="CASCADE"))
    content_md: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class UsageDay(Base):
    __tablename__ = "usage_days"
    __table_args__ = (UniqueConstraint("date", "scene", name="uq_usage_date_scene"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[str] = mapped_column(String(10), index=True)  # YYYY-MM-DD
    scene: Mapped[str] = mapped_column(String(8))  # outline / tutor / quiz / embed
    requests: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
