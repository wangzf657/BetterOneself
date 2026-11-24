"""统一预检与新时序（B6-02/03/06，V0.1.1 技术设计 §2–§4）：分路原因、重试先预检、启动恢复、预估。"""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from openai import APIConnectionError, APIStatusError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import config as config_mod
from app.core.errors import Conflict, Validation
from app.core.llm import ServiceConfig
from app.models import KnowledgePoint, PlanningProposal, Source, SourceChunk, Study, UsageDay
from app.services import outline, pipeline, precheck
from app.services.learning import put_note
from tests.conftest import get_study, make_book_db

CFG = ServiceConfig(base_url="https://x.example/v1", model="m", api_key="sk-test-secret-0000")


def _no_threads(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[str, tuple[Any, ...]]]:
    """拦下后台线程启动并记名，保证用例确定性。"""
    started: list[tuple[str, tuple[Any, ...]]] = []
    for name in ("_start_embed", "_start_precheck", "launch_planning"):
        monkeypatch.setattr(pipeline, name, lambda *a, _n=name, **k: started.append((_n, a)))
    return started


def _count_llm_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """桩模式下所有 LLM 调用的最后一站，记下场景名。"""
    from app.core import stub_llm

    calls: list[str] = []
    real_complete, real_stream = stub_llm.complete, stub_llm.stream

    def complete(messages, *, scene: str) -> str:
        calls.append(scene)
        return real_complete(messages, scene=scene)

    async def stream(messages, *, scene: str):
        calls.append(scene)
        async for piece in real_stream(messages, scene=scene):
            yield piece

    monkeypatch.setattr(stub_llm, "complete", complete)
    monkeypatch.setattr(stub_llm, "stream", stream)
    return calls


def _real_mode(
    monkeypatch: pytest.MonkeyPatch,
    *,
    embed: Callable[..., Any],
    chat: Callable[..., Any],
) -> None:
    """关掉桩，用假客户端顶替探测请求（不触网）。"""
    monkeypatch.setenv("BO_LLM_STUB", "0")
    config_mod.get_config.cache_clear()
    monkeypatch.setattr(precheck, "load_embed_config", lambda db: CFG)
    monkeypatch.setattr(precheck, "load_llm_config", lambda db: CFG)
    client = SimpleNamespace(
        embeddings=SimpleNamespace(create=embed),
        chat=SimpleNamespace(completions=SimpleNamespace(create=chat)),
    )
    monkeypatch.setattr(precheck, "_make_probe_client", lambda cfg: client)


def _http_error(status: int | None) -> Exception:
    request = httpx.Request("POST", "https://x.example/v1/x")
    if status is None:
        return APIConnectionError(request=request)
    return APIStatusError("sk-test-secret-0000", response=httpx.Response(status, request=request), body=None)


def _raises(exc: Exception) -> Callable[..., Any]:
    async def call(**kwargs):
        raise exc

    return call


def _returns(value: Any) -> Callable[..., Any]:
    async def call(**kwargs):
        return value

    return call


async def test_unchecked_book_probes_embedding_only(db, monkeypatch) -> None:
    """未勾选：只检 embedding、零 LLM 调用、原树驻留可学（B6-01/02）。"""
    make_book_db(db)
    started = _no_threads(monkeypatch)
    llm_calls = _count_llm_calls(monkeypatch)
    sid = get_study(db).id

    result = await pipeline.precheck_and_dispatch(sid)

    assert set(result) == {"embedding"} and result["embedding"]["ok"] is True
    db.expire_all()
    study = get_study(db)
    assert study.outline_status == "structure_ready" and study.use_ai_planning is False
    assert started == [("_start_embed", (study.primary_source_id,))]
    assert llm_calls == []


async def test_checked_book_passes_both_lanes_and_waits_for_user(db, monkeypatch) -> None:
    """勾选：两路都检；通过后停在 precheck_ok，规划不自动排（等消耗确认）。"""
    make_book_db(db, use_ai_planning=True)
    started = _no_threads(monkeypatch)
    llm_calls = _count_llm_calls(monkeypatch)
    sid = get_study(db).id

    result = await pipeline.precheck_and_dispatch(sid)

    assert set(result) == {"embedding", "llm"} and all(r["ok"] for r in result.values())
    db.expire_all()
    assert get_study(db).outline_status == "precheck_ok"
    assert [name for name, _ in started] == ["_start_embed"]
    assert llm_calls == []
    assert outline.proposal_view(db, sid) is None


async def test_lane_reasons_are_reported_separately(db, monkeypatch) -> None:
    """未配置 / 请求失败 / 维度不一致分路落库；失败不启动任务、不自动重试（B6-02）。"""
    make_book_db(db, use_ai_planning=True)
    started = _no_threads(monkeypatch)
    sid = get_study(db).id
    source_id = get_study(db).primary_source_id
    assert source_id is not None

    # 未配置：不发任何请求
    monkeypatch.setenv("BO_LLM_STUB", "0")
    config_mod.get_config.cache_clear()
    result = await pipeline.precheck_and_dispatch(sid)
    assert {lane: r["reason"] for lane, r in result.items()} == {
        "embedding": "not_configured",
        "llm": "not_configured",
    }
    db.expire_all()
    study, source = get_study(db), db.get(Source, source_id)
    assert study.outline_status == "precheck_failed" and "未配置 AI 服务" in study.outline_error
    assert source.embed_status == "precheck_failed" and "未配置 embedding 服务" in source.embed_error

    # 请求失败：只报类名与状态码，不带响应体与 key（重试走手动入口，两路都检）
    _real_mode(monkeypatch, embed=_raises(_http_error(None)), chat=_raises(_http_error(401)))
    result = await pipeline.precheck_study(db, sid)
    assert result["embedding"]["reason"] == "request_failed"
    assert result["embedding"]["detail"].startswith("embedding 服务连接失败")
    assert result["llm"]["reason"] == "request_failed" and "HTTP 401" in result["llm"]["detail"]
    assert all("sk-test" not in str(r) for r in result.values())

    # 维度不一致：embedding 拒启动并说明期望/实际；LLM 路不受影响
    vector = SimpleNamespace(embedding=[0.0] * 3)
    _real_mode(
        monkeypatch,
        embed=_returns(SimpleNamespace(data=[vector], usage=SimpleNamespace(prompt_tokens=2))),
        chat=_returns(SimpleNamespace(usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1))),
    )
    result = await pipeline.precheck_study(db, sid)
    assert result["embedding"]["reason"] == "dim_mismatch"
    assert "期望 1024，实际 3" in result["embedding"]["detail"]
    assert result["llm"]["ok"] is True
    db.expire_all()
    study, source = get_study(db), db.get(Source, source_id)
    assert study.outline_status == "precheck_ok" and source.embed_status == "precheck_failed"
    assert started == []
    # 探测用量入账
    usage = {(u.scene, u.requests, u.prompt_tokens) for u in db.query(UsageDay).all()}
    assert ("embed", 1, 2) in usage and ("outline", 1, 1) in usage


async def test_stub_embedding_runs_without_real_config(db) -> None:
    """桩模式下 embedding 不要求真实配置：否则开发与 E2E 里这一路永远是失败。"""
    make_book_db(db)
    source_id = get_study(db).primary_source_id
    assert source_id is not None
    total = db.query(SourceChunk).filter(SourceChunk.source_id == source_id).count()

    await pipeline.embed_source(source_id)

    db.expire_all()
    source = db.get(Source, source_id)
    assert source is not None and source.embed_status == "ready" and source.embed_error is None
    vectors = db.execute(
        text("SELECT COUNT(*) FROM vec_chunks WHERE chunk_id IN"
             " (SELECT id FROM source_chunks WHERE source_id = :s)"),
        {"s": source_id},
    ).scalar()
    assert vectors == total > 0


def test_recover_on_startup_redoes_only_unchecked_precheck(db, monkeypatch) -> None:
    """启动恢复：未预检的重做一次；预检失败的不自动重试（B6-02 验收 4）。"""
    make_book_db(db, use_ai_planning=True)
    make_book_db(db, name="预检失败书", use_ai_planning=True)
    first, second = db.query(Study).order_by(Study.id).all()
    assert first.primary_source_id and second.primary_source_id
    db.get(Source, second.primary_source_id).embed_status = "precheck_failed"
    db.commit()
    started = _no_threads(monkeypatch)

    pipeline.recover_on_startup()

    assert started == [("_start_precheck", (first.id,))]
    db.expire_all()
    assert db.get(Source, second.primary_source_id).embed_status == "precheck_failed"


def test_recover_on_startup_never_schedules_planning(db, monkeypatch) -> None:
    """恢复不自动排规划：规划中 → failed（保树可重试）；待确认的建议原样保留。"""
    make_book_db(db, use_ai_planning=True)
    make_book_db(db, name="待确认书", use_ai_planning=True)
    planning, awaiting = db.query(Study).order_by(Study.id).all()
    assert planning.primary_source_id and awaiting.primary_source_id
    planning.outline_status = "planning"
    awaiting.outline_status = "awaiting_confirm"
    for sid in (planning.primary_source_id, awaiting.primary_source_id):
        db.get(Source, sid).embed_status = "ready"  # embedding 已完成：恢复时无预检可重做
    db.add(
        PlanningProposal(study_id=awaiting.id, thesis="t", ops_json='{"operations": [], "snapshot": {}}')
    )
    db.commit()
    started = _no_threads(monkeypatch)

    pipeline.recover_on_startup()

    assert started == []
    db.expire_all()
    assert db.get(Study, planning.id).outline_status == "failed"
    assert db.get(Study, awaiting.id).outline_status == "awaiting_confirm"
    assert outline.proposal_view(db, awaiting.id) is not None


async def test_reembed_rechecks_before_starting(db, monkeypatch) -> None:
    """重试必先预检：预检不通不启动；可重试状态之外 409（B6-06 验收 1）。"""
    make_book_db(db)
    started = _no_threads(monkeypatch)
    source_id = get_study(db).primary_source_id
    assert source_id is not None
    source = db.get(Source, source_id)

    with pytest.raises(Conflict):  # pending：本就会自动跑，无需重试
        await pipeline.reembed(db, source_id)

    async def down(db_: Session) -> precheck.LaneResult:
        return precheck.LaneResult(False, precheck.REQUEST_FAILED, "连接失败")

    async def up(db_: Session) -> precheck.LaneResult:
        return precheck.LaneResult(True)

    source.embed_status = "precheck_failed"
    db.commit()
    monkeypatch.setattr(precheck, "probe_embedding", down)
    result = await pipeline.reembed(db, source_id)
    assert result["status"] == "precheck_failed" and started == []
    db.expire_all()
    assert db.get(Source, source_id).embed_status == "precheck_failed"

    monkeypatch.setattr(precheck, "probe_embedding", up)
    result = await pipeline.reembed(db, source_id)
    assert result["status"] == "reembed_started"
    assert started == [("_start_embed", (source_id,))]


async def test_manual_precheck_enables_ai_planning(db, monkeypatch) -> None:
    """未勾选后改主意：从星图页手动预检即补启动（B6-06 验收 2）。"""
    make_book_db(db)
    _no_threads(monkeypatch)
    sid = get_study(db).id

    result = await pipeline.precheck_study(db, sid)

    assert set(result) == {"embedding", "llm"}
    db.expire_all()
    study = get_study(db)
    assert study.use_ai_planning is True and study.outline_status == "precheck_ok"


async def test_manual_precheck_gates(db, monkeypatch) -> None:
    """再规划前置：进行中/待确认 409；无结构 422；已应用且有学习证据 409（B6-06 验收 3）。"""
    make_book_db(db, use_ai_planning=True)
    make_book_db(db, name="已应用有证据", use_ai_planning=True)
    make_book_db(db, name="已应用无证据", use_ai_planning=True)
    make_book_db(db, name="无结构", use_ai_planning=True)
    first, with_evidence, clean, empty = db.query(Study).order_by(Study.id).all()
    for s in (with_evidence, clean, empty):
        s.outline_status = "ready"
    db.query(KnowledgePoint).filter(KnowledgePoint.study_id == empty.id).delete()
    put_note(db, db.query(KnowledgePoint).filter_by(study_id=with_evidence.id).first().id, "证据")
    db.commit()
    started = _no_threads(monkeypatch)

    first.outline_status = "planning"
    db.commit()
    with pytest.raises(Conflict):
        await pipeline.precheck_study(db, first.id)
    first.outline_status = "awaiting_confirm"
    db.commit()
    with pytest.raises(Conflict):
        await pipeline.precheck_study(db, first.id)
    with pytest.raises(Validation):
        await pipeline.precheck_study(db, empty.id)
    with pytest.raises(Conflict):
        await pipeline.precheck_study(db, with_evidence.id)
    assert started == []

    result = await pipeline.precheck_study(db, clean.id)
    assert result["llm"]["ok"] is True
    db.expire_all()
    assert db.get(Study, clean.id).outline_status == "precheck_ok"
    assert started == [("_start_embed", (clean.primary_source_id,))]


def test_token_estimates_are_static(book, monkeypatch) -> None:
    """预估只读已落库数据、不调 API（B6-03）；区间公式见技术设计 §4。"""
    db = book
    llm_calls = _count_llm_calls(monkeypatch)
    assert outline.embedding_tokens(1000) == 1200
    # (1000+2000)×1.2 + 2×300 + 500×1.2 + 2000 = 6800 → [×0.9, ×1.3]
    low, high = outline.planning_token_range([1000, 2000], 500)
    assert abs(low - 6120) <= 1 and abs(high - 8840) <= 1
    # 单章摘要输入按 12000 字截断：(12000×1.2 + 300 + 2000)×0.9
    assert abs(outline.planning_token_range([50000], 0)[0] - 15030) <= 1

    estimate = outline.estimate_tokens(db, get_study(db).id)

    assert set(estimate) == {"embedding_tokens", "planning_tokens"}
    low, high = estimate["planning_tokens"]
    assert 0 < low <= high and estimate["embedding_tokens"] > 0
    assert llm_calls == []
