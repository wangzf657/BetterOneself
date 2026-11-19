"""知识点编辑路由(M2-03)+ 依赖图(M2-02)。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import KnowledgePoint, Quiz
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


class SelfReport(BaseModel):
    mastered: bool


@router.post("/kps/{kp_id}/self-report")
def self_report(kp_id: int, data: SelfReport, db: Session = Depends(get_db)) -> dict:
    """自评"我已掌握"(M2-07/M6-03):与系统评估分离存储,标记后不进新计划。"""
    kp = _get_kp(db, kp_id)
    knowledge.set_self_reported(db, kp, data.mastered)
    return {"id": kp.id, "self_reported": kp.self_reported}


@router.post("/kps/{kp_id}/quick-quiz", status_code=201)
def create_quick_quiz(kp_id: int, db: Session = Depends(get_db)) -> dict:
    """快速验证自评(M2-07):1 道客观题。"""
    kp = _get_kp(db, kp_id)
    try:
        quiz = knowledge.quick_quiz(db, kp)
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
    return {"quiz_id": quiz.id, "question": quiz.question}


class QuickAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)


@router.post("/kps/{kp_id}/quick-quiz/{quiz_id}/answer")
def answer_quick_quiz(
    kp_id: int, quiz_id: int, data: QuickAnswer, db: Session = Depends(get_db)
) -> dict:
    """判快速验证答案;不通过 → 回滚自评并补进计划(M2-07)。"""
    from app.services import quiz as quiz_svc

    kp = _get_kp(db, kp_id)
    quiz = db.get(Quiz, quiz_id)
    if quiz is None or quiz.kp_id != kp.id:
        raise HTTPException(status_code=404, detail="quiz not found")
    if quiz.user_answer is not None:
        raise HTTPException(status_code=409, detail="该题已作答")
    graded = quiz_svc.grade(db, quiz, data.answer)
    if not graded.is_correct:
        knowledge.rollback_self_report(db, kp)
    return {"is_correct": graded.is_correct, "self_reported": kp.self_reported}
