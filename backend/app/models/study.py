"""学习项目(M1-01)。"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TimestampMixin


class Study(TimestampMixin, Base):
    __tablename__ = "studies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    goal: Mapped[str] = mapped_column(String(1000))
    # active / archived / completed;取值约束在 Pydantic 层,库内保持宽松便于演进
    status: Mapped[str] = mapped_column(String(16), default="active")
    # 最近一次知识点拆解:M1-06 拆解阶段进度可见,失败可重试
    decompose_status: Mapped[str] = mapped_column(String(16), default="idle")
    decompose_error: Mapped[str | None] = mapped_column(String(500))
