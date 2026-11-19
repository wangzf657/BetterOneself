"""知识点路由(M2-01)。"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.knowledge import KpNode
from app.services import knowledge, studies
from app.services import sources as sources_svc

router = APIRouter(prefix="/api", tags=["knowledge"])


@router.get("/studies/{study_id}/knowledge", response_model=list[KpNode])
def get_tree(study_id: int, db: Session = Depends(get_db)) -> list[dict]:
    if studies.get_study(db, study_id) is None:
        raise HTTPException(status_code=404, detail="study not found")
    return knowledge.get_tree(db, study_id)


@router.get("/studies/{study_id}/decompose-status")
def decompose_status(study_id: int, db: Session = Depends(get_db)):
    """拆解进度(M1-06):解析完成后拆解仍在后台跑,前端据此展示/轮询。"""
    study = studies.get_study(db, study_id)
    if study is None:
        raise HTTPException(status_code=404, detail="study not found")
    return {"status": study.decompose_status, "error": study.decompose_error}


@router.post("/studies/{study_id}/decompose", status_code=202)
def retry_decompose(
    study_id: int, background: BackgroundTasks, db: Session = Depends(get_db)
):
    """拆解失败后的重试入口(M1-06)。"""
    if studies.get_study(db, study_id) is None:
        raise HTTPException(status_code=404, detail="study not found")
    sources_svc.retry_decompose(db, background, study_id)
    return {"status": "running"}
