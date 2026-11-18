"""卡片与复习 API 契约(M3-05, M4-01/02/03)。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CardOrigin = Literal["auto_quiz", "manual_mark", "manual_new"]


class CardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    study_id: int
    kp_id: int
    front: str
    back_md: str
    chunk_id: int | None
    source_id: int | None = None  # 源引用回跳用,api 层填充
    origin: CardOrigin
    status: str
    due: datetime
    state: str | None
    stability: float | None
    difficulty: float | None
    last_review_at: datetime | None


class CardCreate(BaseModel):
    kp_id: int
    front: str = Field(min_length=1, max_length=2000)
    back_md: str = Field(default="", max_length=4000)
    chunk_id: int | None = None
    origin: Literal["manual_mark", "manual_new"] = "manual_mark"


class RateIn(BaseModel):
    rating: int = Field(ge=1, le=4)
