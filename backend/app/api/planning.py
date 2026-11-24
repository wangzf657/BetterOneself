"""AI 规划 API（B6-03/04，V0.1.1 技术设计 §6）：预估、启动、建议确认。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas import (
    Estimate,
    PlanningProposalView,
    PlanningStartBody,
    ProposalApplyBody,
    ProposalApplyResult,
    ProposalDeclineBody,
    ProposalDeclineResult,
)
from app.services import outline, pipeline

router = APIRouter(prefix="/studies/{study_id}/planning", tags=["planning"])


@router.get("/estimate", response_model=Estimate)
def estimate(study_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    return outline.estimate_tokens(db, study_id)


@router.post("/start", status_code=202)
def start(
    study_id: int, body: PlanningStartBody, db: Session = Depends(get_db)
) -> dict[str, str]:
    status = outline.start_planning(
        db, study_id, planned_days=body.planned_days, learning_goal=body.learning_goal
    )
    if status == "planning":
        pipeline.launch_planning(study_id)
    return {"status": status}


@router.get("/proposal", response_model=PlanningProposalView | None)
def proposal(study_id: int, db: Session = Depends(get_db)) -> dict[str, Any] | None:
    return outline.proposal_view(db, study_id)


@router.post("/proposal/apply", response_model=ProposalApplyResult)
def apply(
    study_id: int, body: ProposalApplyBody, db: Session = Depends(get_db)
) -> dict[str, Any]:
    return outline.apply_proposal(db, study_id, body.proposal_id, body.selected)


@router.post("/proposal/decline", response_model=ProposalDeclineResult)
def decline(
    study_id: int, body: ProposalDeclineBody, db: Session = Depends(get_db)
) -> dict[str, Any]:
    return outline.decline_proposal(db, study_id, body.proposal_id)
