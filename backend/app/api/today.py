"""今日任务路由(M3-01/M5-01/02):打开即惰性触发逾期重排。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.plan import TodayOut
from app.services import planning

router = APIRouter(prefix="/api", tags=["today"])


@router.get("/today", response_model=TodayOut)
def today(study_id: int | None = None, db: Session = Depends(get_db)) -> TodayOut:
    view = planning.today_view(db, study_id)
    return TodayOut.model_validate(view)
