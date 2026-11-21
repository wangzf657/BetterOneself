"""学习会话、测验与笔记 API（B3、B4、接口设计 §4/§5）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import Conflict, NotFound
from app.schemas import (
    ChatBody,
    ChunkDetail,
    NodeContent,
    NotePayload,
    NotePut,
    QuizAnswerBody,
    QuizPublic,
    SchemePatch,
    SessionCreate,
    SessionDetail,
)
from app.services import learning, quiz

router = APIRouter(tags=["learning"])


@router.post("/studies/{study_id}/sessions", response_model=SessionDetail)
def create_session(
    study_id: int, body: SessionCreate, db: Session = Depends(get_db)
) -> dict[str, object]:
    session = learning.get_or_create_session(db, study_id, body.kp_id, body.scheme)
    return learning.session_detail(db, session.id)


@router.get("/sessions/{session_id}", response_model=SessionDetail)
def get_session(session_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    return learning.session_detail(db, session_id)


def _sse_response(gen: Any) -> StreamingResponse:
    return StreamingResponse(gen, media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
    })


@router.post("/sessions/{session_id}/opening")
async def session_opening(
    session_id: int, request: Request, db: Session = Depends(get_db)
) -> StreamingResponse:
    session = learning.get_session_or_404(db, session_id)
    if not learning.llm_ready(db):
        from app.core.errors import LLMNotConfigured

        raise LLMNotConfigured()
    existing = await _has_assistant(db, session_id)
    if existing:
        raise Conflict("开场讲解已存在")
    gen = learning.opening_stream(db, session, request.is_disconnected)
    return _sse_response(gen)


async def _has_assistant(db: Session, session_id: int) -> bool:
    from app.models import Message

    return (
        db.query(Message)
        .filter(Message.session_id == session_id, Message.role == "assistant")
        .first()
        is not None
    )


@router.post("/sessions/{session_id}/chat")
async def session_chat(
    session_id: int, body: ChatBody, request: Request, db: Session = Depends(get_db)
) -> StreamingResponse:
    session = learning.get_session_or_404(db, session_id)
    if not learning.llm_ready(db):
        from app.core.errors import LLMNotConfigured

        raise LLMNotConfigured()
    gen = learning.chat_stream(db, session, body.content, request.is_disconnected)
    return _sse_response(gen)


@router.patch("/sessions/{session_id}/scheme", response_model=SessionDetail)
def patch_scheme(
    session_id: int, body: SchemePatch, db: Session = Depends(get_db)
) -> dict[str, object]:
    session = learning.get_session_or_404(db, session_id)
    learning.patch_scheme(db, session, body.scheme)
    return learning.session_detail(db, session_id)


@router.post("/sessions/{session_id}/quizzes", response_model=QuizPublic)
async def create_quiz(session_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    session = learning.get_session_or_404(db, session_id)
    return await quiz.generate_quiz(db, session)


@router.post("/quizzes/{quiz_id}/answer")
async def answer_quiz(
    quiz_id: int, body: QuizAnswerBody, db: Session = Depends(get_db)
) -> dict[str, object]:
    return await quiz.answer_quiz(db, quiz_id, body.answers)


@router.get("/kps/{kp_id}/quizzes")
def kp_quizzes(kp_id: int, db: Session = Depends(get_db)) -> list[dict[str, object]]:
    return quiz.quizzes_of_kp(db, kp_id)


@router.get("/kps/{kp_id}/content", response_model=NodeContent)
def kp_content(kp_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    return learning.node_content(db, kp_id)


@router.get("/chunks/{chunk_id}", response_model=ChunkDetail)
def get_chunk(chunk_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    return learning.get_chunk(db, chunk_id)


@router.get("/kps/{kp_id}/note", response_model=NotePayload)
def get_note(kp_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    return learning.get_note(db, kp_id)


@router.put("/kps/{kp_id}/note", response_model=NotePayload)
def put_note(kp_id: int, body: NotePut, db: Session = Depends(get_db)) -> dict[str, object]:
    return learning.put_note(db, kp_id, body.content_md)


@router.get("/kps/{kp_id}/lighting-evidence")
def lighting_evidence(kp_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    ev = quiz.lighting_evidence(db, kp_id)
    if ev is None:
        raise NotFound("该节点尚无点亮证据")
    return ev
