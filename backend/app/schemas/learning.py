"""学习会话 API 契约(M3-02/03)。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SessionType = Literal["lecture", "feynman", "free"]


class SessionCreate(BaseModel):
    kp_id: int | None = None
    task_id: int | None = None
    session_type: SessionType = "lecture"
    socratic: bool = True


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    study_id: int
    task_id: int | None
    kp_id: int | None
    session_type: SessionType
    socratic_mode: bool
    thread_id: str
    status: str
    started_at: datetime


class SocraticUpdate(BaseModel):
    socratic_mode: bool


class Citation(BaseModel):
    index: int
    chunk_id: int
    heading_path: str
    source_id: int | None


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    citations: list[Citation]


class SessionDetail(SessionOut):
    messages: list[MessageOut]


class ChatIn(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
