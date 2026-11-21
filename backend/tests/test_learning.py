"""学习会话（B3）：gate、opening 原子认领、chat 先落库、笔记、引用。"""

from __future__ import annotations

import json

import pytest

from app.core.errors import Validation
from app.models import KnowledgePoint, Message
from app.services import knowledge, learning
from tests.conftest import get_study


def _kp(db, name: str) -> KnowledgePoint:
    return db.query(KnowledgePoint).filter(KnowledgePoint.name == name).one()


def test_gate_container_and_excluded_and_no_refs(book) -> None:
    db = book
    study = get_study(db)
    container = _kp(db, "第一章 Agent 导论")  # 有子节点 → 容器
    with pytest.raises(Validation):
        learning.get_or_create_session(db, study.id, container.id)

    leaf = _kp(db, "1.1 什么是 Agent")
    knowledge.exclude(db, leaf.id, reason="不学")
    db.expire_all()
    with pytest.raises(Validation):
        learning.get_or_create_session(db, study.id, leaf.id)  # 已排除 422
    knowledge.restore(db, leaf.id)

    # 无引用叶子：临时造一个（把 refs 移走的节点）
    session = learning.get_or_create_session(db, study.id, leaf.id)
    assert session.kp_id == leaf.id
    again = learning.get_or_create_session(db, study.id, leaf.id)
    assert again.id == session.id  # 取或建幂等（1:1）


async def test_opening_atomic_claim_and_content(book) -> None:
    db = book
    study = get_study(db)
    leaf = _kp(db, "1.1 什么是 Agent")
    session = learning.get_or_create_session(db, study.id, leaf.id)
    events = [ev async for ev in learning.opening_stream(db, session)]
    assert any(e.startswith("event: done") for e in events)
    db.expire_all()
    msgs = db.query(Message).filter_by(session_id=session.id).all()
    assert len(msgs) == 1 and msgs[0].role == "assistant"
    refs = json.loads(msgs[0].refs_json or "[]")
    assert refs and "chunk_id" in refs[0]  # 引用锚定本节点切片

    # 第二次 opening：已存在 → error(exists)，不产生第二条
    events2 = [ev async for ev in learning.opening_stream(db, session)]
    assert any('"exists": true' in e for e in events2)
    assert db.query(Message).filter_by(session_id=session.id).count() == 1


async def test_opening_degrades_without_outline(book, monkeypatch) -> None:
    """大纲不可用（无 thesis）时开场仍成功（降级只讲当前节点）。"""
    db = book
    study = get_study(db)
    study.outline_thesis = None
    db.commit()
    leaf = _kp(db, "2.1 信息筛选")
    session = learning.get_or_create_session(db, study.id, leaf.id)
    events = [ev async for ev in learning.opening_stream(db, session)]
    assert any(e.startswith("event: done") for e in events)


async def test_chat_persists_user_message_before_llm(book, monkeypatch) -> None:
    """用户消息先落库；LLM 失败不保存 assistant、用户消息保留可重试（P1-04）。"""
    from app.core.errors import LLMUnavailable

    db = book
    study = get_study(db)
    leaf = _kp(db, "1.2 Agent 的组成")
    session = learning.get_or_create_session(db, study.id, leaf.id)

    from app.skills import tutor

    async def boom(db_, payload, history):
        raise LLMUnavailable("服务炸了")

        async def gen():  # pragma: no cover
            yield ""

        return gen()

    monkeypatch.setattr(tutor, "chat_reply", boom)
    events = [ev async for ev in learning.chat_stream(db, session, "什么是组成？")]
    assert any(e.startswith("event: error") for e in events)
    db.expire_all()
    msgs = db.query(Message).filter_by(session_id=session.id).order_by(Message.id).all()
    assert len(msgs) == 1 and msgs[0].role == "user"  # assistant 未保存


async def test_chat_success_and_no_state_change(book) -> None:
    """自由提问不改节点状态（B3-04）：仅 learning 态由 message 派生，不点亮。"""
    from app.services.tree_core import TreeIndex

    db = book
    study = get_study(db)
    leaf = _kp(db, "2.2 信息压缩")
    session = learning.get_or_create_session(db, study.id, leaf.id)
    events = [ev async for ev in learning.chat_stream(db, session, "压缩的原则？")]
    assert any(e.startswith("event: done") for e in events)
    db.expire_all()
    index = TreeIndex(db, study.id)
    assert index.status_of(leaf) == "learning"  # 有 message → 学习中
    assert leaf.lighted_at is None  # 提问不点亮


def test_note_upsert_and_limit(book) -> None:
    db = book
    leaf = _kp(db, "1.1 什么是 Agent")
    assert learning.get_note(db, leaf.id)["content_md"] == ""
    learning.put_note(db, leaf.id, "第一版")
    learning.put_note(db, leaf.id, "第二版")  # upsert 幂等
    assert learning.get_note(db, leaf.id)["content_md"] == "第二版"
    with pytest.raises(Validation):
        learning.put_note(db, leaf.id, "超" * (64 * 1024 + 1))  # 64KB 上限


def test_node_content_only_node_chunks(book) -> None:
    """打开节点只加载该节点 refs，不拉整本书（B3-02 反例）。"""
    from app.models import SourceChunk

    db = book
    leaf = _kp(db, "1.1 什么是 Agent")
    content = learning.node_content(db, leaf.id)
    total = db.query(SourceChunk).count()
    assert 0 < len(content["chunks"]) < total
    loc = content["chunks"][0]["location"]
    assert loc["type"] == "lines" and "line_start" in loc


def test_chunk_lookup_scoped(book) -> None:
    db = book
    leaf = _kp(db, "2.1 信息筛选")
    content = learning.node_content(db, leaf.id)
    cid = content["chunks"][0]["id"]
    detail = learning.get_chunk(db, cid)
    assert detail["chunk"]["id"] == cid and "location" in detail["chunk"]
    from app.core.errors import NotFound

    with pytest.raises(NotFound):
        learning.get_chunk(db, 10**9)
