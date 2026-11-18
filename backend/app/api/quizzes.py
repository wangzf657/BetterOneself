"""测验路由(M3-04/05)。"""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.helpers import source_of_chunks
from app.db import get_db
from app.models import Quiz
from app.schemas.quiz import AnswerIn, QuizOut, QuizPending
from app.services import learning
from app.services import quiz as quiz_svc

router = APIRouter(prefix="/api", tags=["quizzes"])


def _pending(row: Quiz, source_map: dict[int, int]) -> QuizPending:
    return QuizPending(
        id=row.id,
        session_id=row.session_id,
        kp_id=row.kp_id,
        q_type=row.q_type,  # type: ignore[arg-type]
        question=row.question,
        options=json.loads(row.options_json) if row.options_json else [],
        chunk_id=row.chunk_id,
        source_id=source_map.get(row.chunk_id) if row.chunk_id else None,
        created_at=row.created_at,
    )


def _full(row: Quiz, source_map: dict[int, int]) -> QuizOut:
    pending = _pending(row, source_map)
    return QuizOut(
        **pending.model_dump(),
        answer=row.answer,
        user_answer=row.user_answer,
        is_correct=row.is_correct,
        ai_feedback=row.ai_feedback,
    )


@router.post("/sessions/{session_id}/quizzes", response_model=list[QuizPending], status_code=201)
def generate(session_id: int, db: Session = Depends(get_db)) -> list[QuizPending]:
    session = learning.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    try:
        rows = quiz_svc.generate_for_session(db, session)
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
    smap = source_of_chunks(db, [r.chunk_id for r in rows])
    return [_pending(r, smap) for r in rows]


@router.get("/sessions/{session_id}/quizzes")
def list_quizzes(session_id: int, db: Session = Depends(get_db)) -> list[dict]:
    """未作答返回 pending 形态(无答案),已作答返回完整结果。"""
    rows = db.scalars(
        select(Quiz).where(Quiz.session_id == session_id).order_by(Quiz.id)
    ).fetchall()
    smap = source_of_chunks(db, [r.chunk_id for r in rows])
    return [
        _full(r, smap).model_dump() if r.user_answer is not None else _pending(r, smap).model_dump()
        for r in rows
    ]


@router.post("/quizzes/{quiz_id}/answer", response_model=QuizOut)
def answer(quiz_id: int, data: AnswerIn, db: Session = Depends(get_db)) -> QuizOut:
    row = db.get(Quiz, quiz_id)
    if row is None:
        raise HTTPException(status_code=404, detail="quiz not found")
    if row.user_answer is not None:
        raise HTTPException(status_code=409, detail="该题已作答")
    graded = quiz_svc.grade(db, row, data.answer)
    smap = source_of_chunks(db, [graded.chunk_id])
    return _full(graded, smap)
