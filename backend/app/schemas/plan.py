"""计划与任务 API 契约(M2-04/05/06, M5-01/02)。"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TaskType = Literal["learn", "review_weak", "feynman", "quiz"]
TaskStatus = Literal["pending", "done", "skipped"]


class PlanGenerateIn(BaseModel):
    goal_depth: str = Field(default="", max_length=500)
    deadline: date | None = None
    daily_minutes: int = Field(default=45, ge=10, le=480)
    skipped: bool = False  # 跳过访谈用默认值并明示(M2-04)


class TaskOut(BaseModel):
    id: int
    plan_id: int
    study_id: int
    kp_id: int
    kp_name: str
    task_type: TaskType
    scheduled_date: date
    estimated_minutes: int
    status: TaskStatus
    weak_evidence_id: str | None


class PlanEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    detail_json: str
    created_at: datetime


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    study_id: int
    status: str
    goal_depth: str
    deadline: date | None
    daily_minutes: int
    created_at: datetime


class PlanDetail(PlanOut):
    tasks: list[TaskOut]
    events: list[PlanEventOut]
    warning: str | None  # 每日时长超限提示(M2-05),取自 generated 事件


class TaskMoveIn(BaseModel):
    scheduled_date: date


class RescheduledItem(BaseModel):
    task_id: int
    kp_id: int
    model_from: date = Field(alias="from")
    model_to: date = Field(alias="to")

    model_config = ConfigDict(populate_by_name=True)


class TodayOut(BaseModel):
    date: date
    has_plan: bool = False
    tasks: list[TaskOut]
    rescheduled: list[RescheduledItem]
    due_reviews: int
