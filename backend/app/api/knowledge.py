"""知识点路由(M2-01)。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.knowledge import KpNode
from app.services import knowledge, studies

router = APIRouter(prefix="/api", tags=["knowledge"])


@router.get("/studies/{study_id}/knowledge", response_model=list[KpNode])
def get_tree(study_id: int, db: Session = Depends(get_db)) -> list[dict]:
    if studies.get_study(db, study_id) is None:
        raise HTTPException(status_code=404, detail="study not found")
    return knowledge.get_tree(db, study_id)
