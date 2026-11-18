"""学习会话路由(M3-02/03):SSE 流式对话。"""

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.learning import (
    ChatIn,
    MessageOut,
    SessionCreate,
    SessionDetail,
    SessionOut,
    SocraticUpdate,
)
from app.services import learning, studies

router = APIRouter(prefix="/api", tags=["sessions"])


@router.post("/studies/{study_id}/sessions", response_model=SessionOut, status_code=201)
def create_session(study_id: int, data: SessionCreate, db: Session = Depends(get_db)):
    if studies.get_study(db, study_id) is None:
        raise HTTPException(status_code=404, detail="study not found")
    return SessionOut.model_validate(
        learning.create_session(
            db,
            study_id,
            kp_id=data.kp_id,
            task_id=data.task_id,
            session_type=data.session_type,
            socratic=data.socratic,
        )
    )


@router.get("/sessions/{session_id}", response_model=SessionDetail)
def get_session(session_id: int, db: Session = Depends(get_db)):
    session = learning.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")

    messages = [
        MessageOut(
            id=m.id,
            role=m.role,
            content=m.content,
            citations=json.loads(m.citations_json or "[]"),
        )
        for m in learning.get_messages(db, session_id)
    ]
    return SessionDetail(**SessionOut.model_validate(session).model_dump(), messages=messages)


@router.patch("/sessions/{session_id}/socratic", response_model=SessionOut)
def set_socratic(session_id: int, data: SocraticUpdate, db: Session = Depends(get_db)):
    session = learning.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return SessionOut.model_validate(learning.set_socratic(db, session, data.socratic_mode))


@router.post("/sessions/{session_id}/chat")
def chat(session_id: int, data: ChatIn, db: Session = Depends(get_db)):
    if learning.get_session(db, session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")

    def to_sse():
        for event in learning.chat_stream(session_id, data.content):
            payload = json.dumps(event["data"], ensure_ascii=False)
            yield f"event: {event['event']}\ndata: {payload}\n\n"

    return StreamingResponse(to_sse(), media_type="text/event-stream")
