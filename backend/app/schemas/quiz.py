"""测验 API 契约(M3-04)。未作答不回传 answer,防止泄题。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

QType = Literal["objective", "short_answer"]


class QuizPending(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    kp_id: int
    q_type: QType
    question: str
    options: list[str]
    chunk_id: int | None
    source_id: int | None = None  # 答错回跳源文用,api 层填充
    created_at: datetime


class QuizOut(QuizPending):
    answer: str
    user_answer: str | None
    is_correct: bool | None
    ai_feedback: str | None


class AnswerIn(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)
