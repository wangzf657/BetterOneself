"""学习会话服务(M3-02/03):会话生命周期、上下文装配、SSE 事件流。"""

import json
import uuid
from collections.abc import Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import lecture
from app.db import get_engine
from app.ingest import embedder, vecstore
from app.models import KnowledgeRef, LearningSession, Message, SourceChunk, StudySource

_HISTORY_TURNS = 10
_TOP_K = 6


def create_session(
    db: Session,
    study_id: int,
    kp_id: int | None = None,
    task_id: int | None = None,
    session_type: str = "lecture",
    socratic: bool = True,
) -> LearningSession:
    session = LearningSession(
        study_id=study_id,
        kp_id=kp_id,
        task_id=task_id,
        session_type=session_type,
        socratic_mode=socratic,
        thread_id=uuid.uuid4().hex,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_session(db: Session, session_id: int) -> LearningSession | None:
    return db.get(LearningSession, session_id)


def set_socratic(db: Session, session: LearningSession, enabled: bool) -> LearningSession:
    session.socratic_mode = enabled
    db.commit()
    db.refresh(session)
    return session


def get_messages(db: Session, session_id: int) -> list[Message]:
    return list(
        db.scalars(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.id)
        )
    )


def chat_stream(session_id: int, content: str) -> Iterator[dict]:
    """一轮对话的 SSE 事件生成器:检索 → 流式讲解 → 落库。"""
    with Session(get_engine()) as db:
        session = db.get(LearningSession, session_id)
        if session is None:
            yield {"event": "error", "data": {"detail": "session not found"}}
            return

        db.add(Message(session_id=session.id, role="user", content=content))
        db.commit()

        chunks = _retrieve(db, session, content)
        history = [
            {"role": m.role, "content": m.content}
            for m in get_messages(db, session.id)[-_HISTORY_TURNS:-1]
        ]
        db.close()  # 生成期间不占连接;落库时再开新会话

        parts: list[str] = []
        for piece in lecture.stream_lecture(
            chunks, history, content, session.socratic_mode, session.session_type
        ):
            parts.append(piece)
            yield {"event": "delta", "data": {"text": piece}}
        answer = "".join(parts)
        citations = lecture.extract_citations(answer, chunks)

    with Session(get_engine()) as db:
        db.add(
            Message(
                session_id=session_id,
                role="assistant",
                content=answer,
                citations_json=json.dumps(citations, ensure_ascii=False),
            )
        )
        db.commit()
    yield {"event": "done", "data": {"content": answer, "citations": citations}}


def _retrieve(db: Session, session: LearningSession, query: str) -> list[dict]:
    """知识点引用切片优先保底,再用向量检索补足。"""
    picked: dict[int, dict] = {}
    if session.kp_id:
        rows = db.execute(
            select(SourceChunk)
            .join(KnowledgeRef, KnowledgeRef.chunk_id == SourceChunk.id)
            .where(KnowledgeRef.kp_id == session.kp_id)
            .order_by(SourceChunk.seq)
        ).scalars()
        for c in rows:
            picked[c.id] = _chunk_dict(c)

    source_ids = db.scalars(
        select(StudySource.source_id).where(StudySource.study_id == session.study_id)
    ).fetchall()
    if source_ids and len(picked) < _TOP_K:
        query_vec = embedder.embed_texts([query])[0]
        for cid, _dist in vecstore.search(get_engine(), query_vec, list(source_ids),
                                          k=_TOP_K - len(picked)):
            if cid not in picked:
                chunk = db.get(SourceChunk, cid)
                if chunk is not None:
                    picked[cid] = _chunk_dict(chunk)
    return list(picked.values())[:_TOP_K]


def _chunk_dict(c: SourceChunk) -> dict:
    return {
        "chunk_id": c.id,
        "source_id": c.source_id,
        "heading_path": c.heading_path,
        "content": c.content,
    }
