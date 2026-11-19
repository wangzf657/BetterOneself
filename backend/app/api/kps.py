"""知识点编辑路由(M2-03)+ 依赖图(M2-02)。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import KnowledgePoint
from app.services import knowledge, studies

router = APIRouter(prefix="/api", tags=["kps"])


class KpUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    summary: str | None = Field(default=None, max_length=2000)


class KpCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    summary: str = Field(default="", max_length=2000)
    parent_id: int | None = None


class KpMerge(BaseModel):
    target_id: int


def _get_kp(db: Session, kp_id: int) -> KnowledgePoint:
    kp = db.get(KnowledgePoint, kp_id)
    if kp is None:
        raise HTTPException(status_code=404, detail="kp not found")
    return kp


@router.patch("/kps/{kp_id}")
def update_kp(kp_id: int, data: KpUpdate, db: Session = Depends(get_db)) -> dict:
    kp = knowledge.update_kp(db, _get_kp(db, kp_id), name=data.name, summary=data.summary)
    return {"id": kp.id, "name": kp.name, "summary": kp.summary}


@router.delete("/kps/{kp_id}", status_code=204)
def delete_kp(kp_id: int, db: Session = Depends(get_db)) -> None:
    knowledge.delete_kp(db, _get_kp(db, kp_id))


@router.post("/studies/{study_id}/kps", status_code=201)
def create_kp(study_id: int, data: KpCreate, db: Session = Depends(get_db)) -> dict:
    if studies.get_study(db, study_id) is None:
        raise HTTPException(status_code=404, detail="study not found")
    if data.parent_id is not None:
        parent = _get_kp(db, data.parent_id)
        if parent.study_id != study_id:
            raise HTTPException(status_code=422, detail="父节点不属于该项目")
    kp = knowledge.create_kp(
        db, study_id, name=data.name, summary=data.summary, parent_id=data.parent_id
    )
    return {"id": kp.id, "name": kp.name}


@router.post("/kps/{kp_id}/merge")
def merge_kp(kp_id: int, data: KpMerge, db: Session = Depends(get_db)) -> dict:
    source = _get_kp(db, kp_id)
    target = _get_kp(db, data.target_id)
    try:
        merged = knowledge.merge_kps(db, source, target)
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
    return {"id": merged.id, "name": merged.name}


@router.get("/studies/{study_id}/kp-graph")
def get_graph(study_id: int, db: Session = Depends(get_db)) -> dict:
    return knowledge.get_graph(db, study_id)
