"""学习会话、消息与测验(M3-02~07)。类名 LearningSession 避开 db.Session。"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class LearningSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    study_id: Mapped[int] = mapped_column(
        ForeignKey("studies.id", ondelete="CASCADE"), index=True
    )
    # 自由提问无任务(M3-06)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"))
    kp_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE")
    )
    # lecture / feynman / free
    session_type: Mapped[str] = mapped_column(String(16), default="lecture")
    # 会话级苏格拉底开关,默认引导式(M3-03)
    socratic_mode: Mapped[bool] = mapped_column(Boolean, default=True)
    # LangGraph 检查点线程,断点续聊
    thread_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    # user / assistant
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    # chunk_id 数组,前端渲染引用角标
    citations_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    kp_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"), index=True
    )
    # objective / short_answer
    q_type: Mapped[str] = mapped_column(String(16))
    question: Mapped[str] = mapped_column(Text)
    options_json: Mapped[str | None] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    user_answer: Mapped[str | None] = mapped_column(Text)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    # 简答由 AI 评分给评语(M3-04)
    ai_feedback: Mapped[str | None] = mapped_column(Text)
    # 答错回跳的源文位置
    chunk_id: Mapped[int | None] = mapped_column(ForeignKey("source_chunks.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
