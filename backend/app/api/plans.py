"""计划/任务路由(M2-04/05/06, M5-01/02)。"""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import KnowledgePoint, Plan, Task
from app.schemas.plan import (
    PlanDetail,
    PlanEventOut,
    PlanGenerateIn,
    PlanOut,
    TaskMoveIn,
    TaskOut,
)
from app.services import planning, studies

router = APIRouter(prefix="/api", tags=["plans"])


def _task_out(db: Session, t: Task) -> TaskOut:
    kp = db.get(KnowledgePoint, t.kp_id)
    return TaskOut(
        id=t.id,
        plan_id=t.plan_id,
        study_id=t.study_id,
        kp_id=t.kp_id,
        kp_name=kp.name if kp else "",
        task_type=t.task_type,  # type: ignore[arg-type]
        scheduled_date=t.scheduled_date,
        estimated_minutes=t.estimated_minutes,
        status=t.status,  # type: ignore[arg-type]
        weak_evidence_id=t.weak_evidence_id,
    )


def _plan_detail(db: Session, plan: Plan) -> PlanDetail:
    events = planning.list_events(db, plan.id)
    warning = None
    for e in events:
        if e.event_type == "generated":
            warning = json.loads(e.detail_json).get("warning")
    return PlanDetail(
        **PlanOut.model_validate(plan).model_dump(),
        tasks=[_task_out(db, t) for t in planning.list_tasks(db, plan.id)],
        events=[PlanEventOut.model_validate(e) for e in events],
        warning=warning,
    )


@router.post("/studies/{study_id}/plans", response_model=PlanDetail, status_code=201)
def generate_plan(study_id: int, data: PlanGenerateIn, db: Session = Depends(get_db)) -> PlanDetail:
    if studies.get_study(db, study_id) is None:
        raise HTTPException(status_code=404, detail="study not found")
    plan, _warning = planning.generate_plan(
        db,
        study_id,
        goal_depth=data.goal_depth,
        deadline=data.deadline,
        daily_minutes=data.daily_minutes,
        skipped=data.skipped,
    )
    return _plan_detail(db, plan)


@router.get("/studies/{study_id}/plan", response_model=PlanDetail)
def get_plan(study_id: int, db: Session = Depends(get_db)) -> PlanDetail:
    plan = planning.get_current_plan(db, study_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="no plan yet")
    return _plan_detail(db, plan)


@router.post("/plans/{plan_id}/confirm", response_model=PlanDetail)
def confirm_plan(plan_id: int, db: Session = Depends(get_db)) -> PlanDetail:
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="plan not found")
    return _plan_detail(db, planning.confirm_plan(db, plan))


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def move_task(task_id: int, data: TaskMoveIn, db: Session = Depends(get_db)) -> TaskOut:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return _task_out(db, planning.move_task(db, task, data.scheduled_date))


@router.post("/tasks/{task_id}/complete", response_model=TaskOut)
def complete_task(task_id: int, db: Session = Depends(get_db)) -> TaskOut:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    from app.db import utcnow

    task.status = "done"
    task.completed_at = utcnow()
    db.commit()
    db.refresh(task)
    return _task_out(db, task)
