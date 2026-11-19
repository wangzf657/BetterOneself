"""督促路由(M5-03/05/06):摘要、周复盘、回炉。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Summary
from app.services import nudges, studies

router = APIRouter(prefix="/api", tags=["nudges"])


class SummaryOut(BaseModel):
    id: int
    summary_type: str
    period_date: str
    content_md: str


@router.get("/studies/{study_id}/summaries")
def list_summaries(study_id: int, db: Session = Depends(get_db)) -> list[dict]:
    """惰性生成当日摘要与本周复盘后返回全部(M5-03/05)。"""
    if studies.get_study(db, study_id) is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="study not found")
    nudges.ensure_daily_summary(db, study_id)
    nudges.ensure_weekly_review(db, study_id)
    rows = db.scalars(
        select(Summary)
        .where(Summary.study_id == study_id)
        .order_by(Summary.summary_type, Summary.period_date.desc())
    ).fetchall()
    return [
        {
            "id": r.id,
            "summary_type": r.summary_type,
            "period_date": str(r.period_date),
            "content_md": r.content_md,
        }
        for r in rows
    ]


@router.get("/studies/{study_id}/inactivity")
def inactivity(study_id: int, db: Session = Depends(get_db)) -> dict:
    return nudges.check_inactivity(db, study_id)


@router.post("/studies/{study_id}/return-from-break")
def return_from_break(study_id: int, db: Session = Depends(get_db)) -> dict:
    """回炉(M5-06):剩余任务重排到今天起,薄弱卡片提到今天。"""
    return nudges.return_from_break(db, study_id)
