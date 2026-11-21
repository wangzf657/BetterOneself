"""学习会话服务（B3、技术方案 §7.1/7.2/7.4）：1:1 持久会话、SSE 生成、三层上下文、笔记。"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_config
from app.core.errors import LLMNotConfigured, NotFound, Validation
from app.core.llm import llm_configured
from app.models import KnowledgePoint, Message, Note, Session_, SourceChunk, Study, utcnow
from app.services import quiz as quiz_service
from app.services.tree_core import TreeIndex

logger = logging.getLogger(__name__)

REF_TOP_K = 6
REF_CHAR_BUDGET = 14000
SOURCE_CHAR_CAP = 3200
SUMMARY_CHAR_BUDGET = 4000
HISTORY_LIMIT = 20
NOTE_MAX_BYTES = 64 * 1024
_CITE = re.compile(r"\[(\d{1,2})\]")

# 进程内每会话一把锁：同一会话串行生成，双击排队（P1-04）
_locks: dict[int, asyncio.Lock] = {}


def _lock_for(session_id: int) -> asyncio.Lock:
    lock = _locks.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        _locks[session_id] = lock
    return lock


def llm_ready(db: Session) -> bool:
    return get_config().llm_stub or llm_configured(db)


def _require_llm(db: Session) -> None:
    if not llm_ready(db):
        raise LLMNotConfigured()


def get_or_create_session(
    db: Session, study_id: int, kp_id: int, scheme: str | None = None
) -> Session_:
    """幂等取或建（决策 #27 gate：容器/已排除/无引用 422）。"""
    study = db.get(Study, study_id)
    if study is None:
        raise NotFound("学习项目不存在")
    kp = db.get(KnowledgePoint, kp_id)
    if kp is None or kp.study_id != study_id:
        raise NotFound("节点不存在")
    index = TreeIndex(db, study_id)
    if kp.excluded or index.is_effectively_excluded(kp.id):
        raise Validation("该节点已排除：历史会话只读可回看，不能开始新的学习")
    if not index.is_valid_unit(kp.id):
        raise Validation(
            "该节点当前不能学习（容器节点或原文引用未就绪）"
            if index.children.get(kp.id)
            else "该节点的原文引用尚未就绪，请稍候"
        )
    existing = db.query(Session_).filter(Session_.kp_id == kp_id).one_or_none()
    if existing is not None:
        if scheme is not None and scheme in {"guided", "lecture", "drill"}:
            existing.scheme = scheme
            db.commit()
        return existing
    if scheme is not None and scheme not in {"guided", "lecture", "drill"}:
        raise Validation("学习方法只能是 guided / lecture / drill")
    session = Session_(study_id=study_id, kp_id=kp_id, scheme=scheme or study.scheme)
    db.add(session)
    db.commit()
    return session


def get_session_or_404(db: Session, session_id: int) -> Session_:
    session = db.get(Session_, session_id)
    if session is None:
        raise NotFound("会话不存在")
    return session


def serialize_message(m: Message) -> dict[str, Any]:
    refs: list[dict[str, Any]] = []
    if m.refs_json:
        try:
            refs = json.loads(m.refs_json)
        except json.JSONDecodeError:
            refs = []
    return {
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "refs": refs,
        "stopped": m.stopped,
        "created_at": m.created_at,
    }


def session_detail(db: Session, session_id: int) -> dict[str, Any]:
    session = get_session_or_404(db, session_id)
    messages = (
        db.query(Message).filter(Message.session_id == session_id).order_by(Message.id).all()
    )
    quizzes = quiz_service.quizzes_of_session(db, session_id)
    kp = db.get(KnowledgePoint, session.kp_id)
    index = TreeIndex(db, session.study_id)
    return {
        "session": {
            "id": session.id,
            "study_id": session.study_id,
            "kp_id": session.kp_id,
            "kp_name": kp.name if kp else None,
            "kp_path": index.path_names(session.kp_id) if kp else [],
            "scheme": session.scheme,
            "excluded": index.is_effectively_excluded(session.kp_id),
        },
        "messages": [serialize_message(m) for m in messages],
        "quizzes": quizzes,
    }


def node_content(db: Session, kp_id: int) -> dict[str, Any]:
    """节点原文：只返回该节点 refs 切片，不拉整本书（B3-02）。"""
    from app.models import KnowledgeRef

    kp = db.get(KnowledgePoint, kp_id)
    if kp is None:
        raise NotFound("节点不存在")
    rows = (
        db.query(KnowledgeRef, SourceChunk)
        .join(SourceChunk, SourceChunk.id == KnowledgeRef.chunk_id)
        .filter(KnowledgeRef.kp_id == kp_id)
        .order_by(SourceChunk.sort_order)
        .all()
    )
    chunks = [
        {
            "id": c.id,
            "title": c.title,
            "content": c.content,
            "location": json.loads(c.location),
            "level_path": c.level_path,
        }
        for _r, c in rows
    ]
    return {"kp_id": kp_id, "kp_name": kp.name, "chunks": chunks}


def get_chunk(db: Session, chunk_id: int) -> dict[str, Any]:
    chunk = db.get(SourceChunk, chunk_id)
    if chunk is None:
        raise NotFound("原文切片不存在")
    return {
        "chunk": {
            "id": chunk.id,
            "title": chunk.title,
            "content": chunk.content,
            "location": json.loads(chunk.location),
        },
        "source_id": chunk.source_id,
    }


async def build_context(
    db: Session, session: Session_, question: str | None
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """三层上下文（技术方案 §8）：节点 refs 保底 + 章节摘要地图 + 向量补足。"""
    from app.models import KnowledgeRef
    from app.services.pipeline import search_similar

    study = db.get(Study, session.study_id)
    assert study is not None
    index = TreeIndex(db, session.study_id)
    kp = db.get(KnowledgePoint, session.kp_id)
    assert kp is not None

    rows = (
        db.query(KnowledgeRef, SourceChunk)
        .join(SourceChunk, SourceChunk.id == KnowledgeRef.chunk_id)
        .filter(KnowledgeRef.kp_id == kp.id)
        .order_by(SourceChunk.sort_order)
        .all()
    )
    node_chunks = [
        {"chunk_id": c.id, "title": c.title, "content": c.content,
         "location": json.loads(c.location)}
        for _r, c in rows
    ]

    selected = node_chunks
    if len(node_chunks) > REF_TOP_K:
        if question:
            ids = await search_similar(
                db, _source_id_of(db, session.study_id), question,
                k=REF_TOP_K, exclude_ids=set(),
            )
            wanted = {i for i in ids if i in {c["chunk_id"] for c in node_chunks}}
            if wanted:
                picked = [c for c in node_chunks if c["chunk_id"] in wanted]
                rest = [c for c in node_chunks if c["chunk_id"] not in wanted]
                selected = picked + rest[: max(REF_TOP_K - len(picked), 0)]
            else:
                selected = node_chunks[:REF_TOP_K]
        else:
            selected = node_chunks[:REF_TOP_K]

    # 整块取舍 + 预算（不做静默中部截断）
    sources: list[dict[str, Any]] = []
    used = 0
    for c in selected:
        content = c["content"][:SOURCE_CHAR_CAP]
        if used + len(content) > REF_CHAR_BUDGET:
            continue
        sources.append({**c, "content": content})
        used += len(content)

    # 向量补足：其他节点细节（引用仍限本书）
    if question:
        exclude = {c["chunk_id"] for c in node_chunks}
        extra_ids = await search_similar(
            db, _source_id_of(db, session.study_id), question, k=3, exclude_ids=exclude
        )
        if extra_ids:
            extras = db.query(SourceChunk).filter(SourceChunk.id.in_(extra_ids)).all()
            for chunk in extras:
                sources.append(
                    {"chunk_id": chunk.id, "title": chunk.title,
                     "content": chunk.content[:SOURCE_CHAR_CAP],
                     "location": json.loads(chunk.location)}
                )

    summaries = {
        k.name: k.chapter_summary
        for k in index.kps
        if k.is_chapter and k.chapter_summary
    }
    summary_text = json.dumps(summaries, ensure_ascii=False)[:SUMMARY_CHAR_BUDGET]

    payload = {
        "book_title": study.name,
        "thesis": study.outline_thesis,
        "chapter_summaries": summaries if summary_text else None,
        "node_path": index.path_names(kp.id),
        "node_title": kp.name,
        "scheme": session.scheme,
        "sources": sources,
        "question": question,
    }
    return payload, sources


def _source_id_of(db: Session, study_id: int) -> int:
    study = db.get(Study, study_id)
    assert study is not None and study.primary_source_id is not None
    return study.primary_source_id


def _cited_refs(text: str, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    nums = {int(n) for n in _CITE.findall(text)}
    refs = []
    for n in sorted(nums):
        if 1 <= n <= len(sources):
            s = sources[n - 1]
            refs.append(
                {
                    "no": n,
                    "chunk_id": s["chunk_id"],
                    "title": s["title"],
                    "location": s["location"],
                    "quote": s["content"][:100],
                }
            )
    return refs


def _touch_pointers(db: Session, session: Session_) -> None:
    study = db.get(Study, session.study_id)
    assert study is not None
    study.last_kp_id = session.kp_id
    study.last_learned_at = utcnow()


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


async def opening_stream(
    db: Session, session: Session_, is_disconnected: Any = None
) -> AsyncIterator[str]:
    """首条讲解（B3-01）：原子认领、双击幂等、失败不伪造用户消息。"""
    from app.skills import tutor

    async with _lock_for(session.id):
        existing = (
            db.query(Message)
            .filter(Message.session_id == session.id, Message.role == "assistant")
            .first()
        )
        if existing is not None:
            yield _sse("error", {"detail": "开场讲解已存在", "retryable": False,
                                 "exists": True})
            return
        _require_llm(db)
        payload, sources = await build_context(db, session, None)
        full: list[str] = []
        stopped = False
        try:
            stream = await tutor.opening(db, payload)
            async for delta in stream:
                if is_disconnected is not None and await is_disconnected():
                    stopped = True
                    break
                full.append(delta)
                yield _sse("delta", {"text": delta})
        except Exception as e:
            from app.core.errors import AppError

            logger.exception("开场讲解生成失败 session=%s", session.id)
            detail = e.detail if isinstance(e, AppError) else "生成讲解失败，请重试"
            yield _sse("error", {"detail": detail, "retryable": True})
            return
        content = "".join(full)
        if content.strip():
            msg = Message(
                session_id=session.id,
                role="assistant",
                content=content,
                refs_json=json.dumps(_cited_refs(content, sources), ensure_ascii=False),
                stopped=stopped,
            )
            db.add(msg)
            _touch_pointers(db, session)
            db.commit()
            saved = (
                db.query(Message)
                .filter(Message.session_id == session.id, Message.role == "assistant")
                .order_by(Message.id.desc())
                .first()
            )
            assert saved is not None
            yield _sse("done", {"message": serialize_message(saved)})
        else:
            yield _sse("error", {"detail": "生成讲解失败，请重试", "retryable": True})


async def chat_stream(
    db: Session, session: Session_, content: str, is_disconnected: Any = None
) -> AsyncIterator[str]:
    """自由提问（B3-04）：用户消息先落库；完成或停止保存；失败不存 assistant。"""
    from app.skills import tutor

    content = content.strip()
    if not content or len(content) > 8000:
        raise Validation("消息内容长度需在 1–8000 字之间")

    async with _lock_for(session.id):
        user_msg = Message(session_id=session.id, role="user", content=content)
        db.add(user_msg)
        _touch_pointers(db, session)
        db.commit()  # 调用 LLM 之前提交入库（P1-04）
        _require_llm(db)

        history = [
            {"role": m.role, "content": m.content}
            for m in db.query(Message)
            .filter(Message.session_id == session.id)
            .order_by(Message.id.desc())
            .limit(HISTORY_LIMIT)
            .all()
        ][::-1]
        payload, sources = await build_context(db, session, content)
        full: list[str] = []
        stopped = False
        try:
            stream = await tutor.chat_reply(db, payload, history)
            async for delta in stream:
                if is_disconnected is not None and await is_disconnected():
                    stopped = True
                    break
                full.append(delta)
                yield _sse("delta", {"text": delta})
        except Exception as e:
            from app.core.errors import AppError

            logger.exception("回答生成失败 session=%s", session.id)
            detail = e.detail if isinstance(e, AppError) else "生成回答失败，请重试"
            yield _sse("error", {"detail": detail, "retryable": True})
            return
        text = "".join(full)
        if text.strip():
            msg = Message(
                session_id=session.id,
                role="assistant",
                content=text,
                refs_json=json.dumps(_cited_refs(text, sources), ensure_ascii=False),
                stopped=stopped,
            )
            db.add(msg)
            _touch_pointers(db, session)
            db.commit()
            saved = (
                db.query(Message)
                .filter(Message.session_id == session.id, Message.role == "assistant")
                .order_by(Message.id.desc())
                .first()
            )
            assert saved is not None
            yield _sse("done", {"message": serialize_message(saved)})
        else:
            yield _sse("error", {"detail": "生成回答失败，请重试", "retryable": True})


def patch_scheme(db: Session, session: Session_, scheme: str) -> Session_:
    if scheme not in {"guided", "lecture", "drill"}:
        raise Validation("学习方法只能是 guided / lecture / drill")
    session.scheme = scheme
    db.commit()
    return session


def get_note(db: Session, kp_id: int) -> dict[str, Any]:
    from app.models import KnowledgeRef  # noqa: F401  保持导入一致性

    kp = db.get(KnowledgePoint, kp_id)
    if kp is None:
        raise NotFound("节点不存在")
    note = db.query(Note).filter(Note.kp_id == kp_id).one_or_none()
    return {
        "kp_id": kp_id,
        "content_md": note.content_md if note else "",
        "updated_at": note.updated_at if note else None,
    }


def put_note(db: Session, kp_id: int, content_md: str) -> dict[str, Any]:
    kp = db.get(KnowledgePoint, kp_id)
    if kp is None:
        raise NotFound("节点不存在")
    if len(content_md.encode("utf-8")) > NOTE_MAX_BYTES:
        raise Validation("笔记超过 64KB 上限")
    note = db.query(Note).filter(Note.kp_id == kp_id).one_or_none()
    if note is None:
        note = Note(study_id=kp.study_id, kp_id=kp_id, content_md=content_md)
        db.add(note)
    else:
        note.content_md = content_md
    db.commit()  # 笔记不参与点亮与任何统计（决策 #26）
    return {"kp_id": kp_id, "content_md": note.content_md, "updated_at": note.updated_at}


__all__ = [
    "chat_stream",
    "get_chunk",
    "get_note",
    "get_or_create_session",
    "get_session_or_404",
    "llm_ready",
    "node_content",
    "opening_stream",
    "patch_scheme",
    "put_note",
    "session_detail",
]
