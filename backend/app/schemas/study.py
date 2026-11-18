"""学习项目 API 契约(M1-01)。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

StudyStatus = Literal["active", "archived", "completed"]


class StudyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=1, max_length=1000)


class StudyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    goal: str | None = Field(default=None, min_length=1, max_length=1000)
    status: StudyStatus | None = None


class StudyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    goal: str
    status: StudyStatus
    created_at: datetime
    updated_at: datetime
