"""API 集成冒烟（TestClient）：路由、错误码、SSE、跨书保护。"""

from __future__ import annotations

import io
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import BOOK, api_client


@pytest.fixture(autouse=True)
def _no_background_threads(monkeypatch) -> list[tuple[str, tuple[Any, ...]]]:
    """后台线程一律拦下并记名：用例自己决定何时驱动预检/规划。"""
    from app.services import pipeline

    started: list[tuple[str, tuple[Any, ...]]] = []
    for name in ("_start_embed", "_start_precheck", "launch_planning"):
        monkeypatch.setattr(pipeline, name, lambda *a, _n=name, **k: started.append((_n, a)))
    return started


def _client() -> TestClient:
    return api_client()


def _create_book(c: TestClient, name: str = "API 书", *, use_ai_planning: bool = False) -> dict:
    r = c.post(
        "/api/studies",
        data={"name": name, "use_ai_planning": str(use_ai_planning).lower()},
        files={"file": ("b.txt", io.BytesIO(BOOK.encode("utf-8")), "text/plain")},
        headers={"Idempotency-Key": f"api-{abs(hash(name)) & 0xFFFFFF}"},
    )
    assert r.status_code in (200, 201), r.text
    return r.json()


def test_studies_crud_and_progress() -> None:
    with _client() as c:
        sid = _create_book(c)["id"]
        r = c.get(f"/api/studies/{sid}/progress")
        assert r.status_code == 200
        assert r.json()["parse"]["status"] == "parsed"
        listing = c.get("/api/studies").json()
        assert listing and listing[0]["name"] == "API 书"
        patched = c.patch(f"/api/studies/{sid}", json={"scheme": "drill"})
        assert patched.json()["scheme"] == "drill"
        missing = c.get("/api/studies/9999")
        assert missing.status_code == 404


def test_knowledge_tree_and_outline_status(_no_background_threads) -> None:
    with _client() as c:
        sid = _create_book(c)["id"]
        tree = c.get(f"/api/studies/{sid}/knowledge").json()
        assert tree["progress"]["total"] >= 5
        assert all("status" in n for n in tree["nodes"])

        status = c.get(f"/api/studies/{sid}/outline-status").json()
        assert status["status"] == "structure_ready"  # 未勾选 AI 规划：原树驻留，可直接学
        progress = c.get(f"/api/studies/{sid}/progress").json()
        assert progress["outline"]["ai_planning"] is False and "stage" in progress["outline"]

        events = c.get(f"/api/studies/{sid}/outline/events").json()
        assert any(e["event_type"] == "structure_built" for e in events)


def test_planning_flow_endpoints(_no_background_threads) -> None:
    """B6-03/04 接口闭环：预检 → 预估 → 启动 → 建议确认 → 应用；非法输入 422、越序 409。"""
    import asyncio

    from app.services import outline

    started = _no_background_threads
    with _client() as c:
        created = _create_book(c, "AI 规划书", use_ai_planning=True)
        sid = created["id"]
        assert created["use_ai_planning"] is True and created["planned_days"] == 10
        base = f"/api/studies/{sid}/planning"
        start = {"planned_days": 20, "learning_goal": "学透这本书"}

        # 越序：未预检不能启动；没有建议可拒绝
        assert c.post(f"{base}/start", json=start).status_code == 409
        assert c.get(f"{base}/proposal").json() is None
        assert c.post(f"{base}/proposal/decline", json={"proposal_id": 1}).status_code == 409
        # 天数 1–365、目标 1–200 字
        for bad in (
            {"planned_days": 0, "learning_goal": "g"},
            {"planned_days": 366, "learning_goal": "g"},
            {"planned_days": 10, "learning_goal": "  "},
            {"planned_days": 10, "learning_goal": "长" * 201},
        ):
            assert c.post(f"{base}/start", json=bad).status_code == 422

        precheck = c.post(f"/api/studies/{sid}/precheck")
        assert precheck.status_code == 200 and precheck.json()["llm"]["ok"] is True
        assert c.get(f"/api/studies/{sid}").json()["outline_status"] == "precheck_ok"
        assert [name for name, _ in started] == ["_start_precheck", "_start_embed"]

        estimate = c.get(f"{base}/estimate").json()
        low, high = estimate["planning_tokens"]
        assert 0 < low <= high and estimate["embedding_tokens"] > 0

        launched = c.post(f"{base}/start", json=start)
        assert launched.status_code == 202 and launched.json() == {"status": "planning"}
        assert started[-1] == ("launch_planning", (sid,))
        assert c.get(f"/api/studies/{sid}").json()["outline_status"] == "planning"
        assert c.post(f"{base}/start", json=start).status_code == 409  # 进行中

        assert asyncio.run(outline.generate_proposal(sid)) == "awaiting_confirm"
        view = c.get(f"{base}/proposal").json()
        pid = view["proposal_id"]
        assert view["thesis"] and [op["op"] for op in view["operations"]] == ["group", "merge"]
        assert all("flagged" in op and "flag_reason" in op for op in view["operations"])
        assert c.post(f"/api/studies/{sid}/precheck").status_code == 409  # 待确认期间不让路
        assert c.post(f"{base}/start", json=start).status_code == 409

        assert c.post(f"{base}/proposal/apply", json={"proposal_id": pid, "selected": []}).status_code == 422
        applied = c.post(f"{base}/proposal/apply", json={"proposal_id": pid, "selected": [0]})
        assert applied.status_code == 200 and applied.json()["status"] == "ready"
        assert c.get(f"/api/studies/{sid}/outline-status").json()["status"] == "ready"
        assert c.get(f"{base}/proposal").json() is None
        declined = c.post(f"{base}/proposal/decline", json={"proposal_id": pid})
        assert declined.status_code == 409


def test_reembed_endpoint_checks_before_starting(_no_background_threads) -> None:
    from app.core.db import get_session_local
    from app.models import Source

    started = _no_background_threads
    with _client() as c:
        sid = _create_book(c)["id"]
        source_id = next(s["source_id"] for s in c.get("/api/studies").json() if s["id"] == sid)

        r = c.post(f"/api/sources/{source_id}/reembed")
        assert r.status_code == 409  # pending：会自动跑，无需重试

        with get_session_local()() as db:
            db.get(Source, source_id).embed_status = "precheck_failed"
            db.commit()
        r = c.post(f"/api/sources/{source_id}/reembed")
        assert r.status_code == 202 and r.json() == {
            "status": "reembed_started",
            "embedding": {"ok": True, "reason": None, "detail": None},
        }
        assert started == [("_start_precheck", (sid,)), ("_start_embed", (source_id,))]


def test_kp_editing_endpoints() -> None:
    with _client() as c:
        sid = _create_book(c)["id"]
        tree = c.get(f"/api/studies/{sid}/knowledge").json()

        def walk(nodes):
            for n in nodes:
                yield n
                yield from walk(n["children"])

        units = [n for n in walk(tree["nodes"]) if n["is_learning_unit"]]
        leaf = units[0]

        renamed = c.patch(f"/api/kps/{leaf['id']}", json={"name": "改名后的节点"})
        assert renamed.status_code == 200 and renamed.json()["name"] == "改名后的节点"

        impact = c.get(f"/api/kps/{leaf['id']}/exclude-impact").json()
        excluded = c.post(f"/api/kps/{leaf['id']}/exclude", json={"reason": "r"}).json()
        assert excluded["progress_after"]["total"] == impact["progress_after"]["total"]  # 预览=应用
        again = c.post(f"/api/kps/{leaf['id']}/exclude", json={})
        assert again.status_code == 409  # 已排除再排除
        restored = c.post(f"/api/kps/{leaf['id']}/restore").json()
        assert restored["progress_after"]["total"] == impact["progress_before"]["total"]

        bad = c.patch(f"/api/kps/{leaf['id']}", json={"name": ""})
        assert bad.status_code == 422  # 空名 422
        assert c.get("/api/kps/999999/exclude-impact").status_code == 404


def test_session_flow_sse_and_quiz() -> None:
    with _client() as c:
        sid = _create_book(c)["id"]
        tree = c.get(f"/api/studies/{sid}/knowledge").json()

        def walk(nodes):
            for n in nodes:
                yield n
                yield from walk(n["children"])

        leaf = next(n for n in walk(tree["nodes"]) if n["is_learning_unit"] and n["name"].startswith("1.1"))

        s = c.post(f"/api/studies/{sid}/sessions", json={"kp_id": leaf["id"]})
        assert s.status_code == 200
        session_id = s.json()["session"]["id"]

        opening = c.post(f"/api/sessions/{session_id}/opening")
        assert opening.status_code == 200
        assert "event: done" in opening.text
        # 未配置真实 LLM 时不泄露密钥；桩模式下无明文 key 出现
        assert "sk-" not in opening.text

        # opening 幂等：再调用返回 409
        dup = c.post(f"/api/sessions/{session_id}/opening")
        assert dup.status_code == 409

        quiz = c.post(f"/api/sessions/{session_id}/quizzes").json()
        assert quiz["graded_count"] == 4 and quiz["pass_line"] == 3
        answers = [
            {"no": 1, "choice": "B"}, {"no": 2, "choice": "C"},
            {"no": 3, "choice": False}, {"no": 4, "choice": False},
            {"no": 5, "text": "练习作答"},
        ]
        answered = c.post(f"/api/quizzes/{quiz['quiz_id']}/answer", json={"answers": answers}).json()
        assert answered["passed"] is True and answered["lighted"]["already_lighted"] is False

        # 会话详情：测验卡带判分面；刷新一致性（再次 GET 相同）
        d1 = c.get(f"/api/sessions/{session_id}").json()
        d2 = c.get(f"/api/sessions/{session_id}").json()
        assert d1 == d2

        # 历次测验回看（QuizAnswered 面）
        hist = c.get(f"/api/kps/{leaf['id']}/quizzes").json()
        assert hist and hist[0]["per_question"]


def test_cross_study_guard() -> None:
    with _client() as c:
        sid1 = _create_book(c, "书一")["id"]
        sid2 = _create_book(c, "书二")["id"]
        tree1 = c.get(f"/api/studies/{sid1}/knowledge").json()

        def walk(nodes):
            for n in nodes:
                yield n
                yield from walk(n["children"])

        leaf1 = next(n for n in walk(tree1["nodes"]) if n["is_learning_unit"])
        # 用书一的节点在书二开会话 → 404/422，禁止跨书挂接
        r = c.post(f"/api/studies/{sid2}/sessions", json={"kp_id": leaf1["id"]})
        assert r.status_code in (404, 422)


def test_settings_and_usage_endpoints() -> None:
    with _client() as c:
        got = c.get("/api/settings").json()
        assert "llm" in got and "embed" in got
        put = c.put("/api/settings", json={"llm": {"base_url": "https://x.example/v1", "model": "m"}})
        assert put.status_code == 200
        assert c.get("/api/usage").json() == []


def test_settings_partial_update_keeps_other_fields() -> None:
    """BUG-001 回归：部分保存不得清空未提交字段（P1-06 三语义）。"""
    with _client() as c:
        # 全量配置
        r = c.put(
            "/api/settings",
            json={"llm": {"base_url": "https://x.example/v1", "model": "m1", "api_key": "sk-QAtest1234567890"}},
        )
        assert r.status_code == 200
        got = r.json()["llm"]
        assert got["base_url"] == "https://x.example/v1" and got["model"] == "m1"
        assert got["api_key"] and got["api_key"].startswith("sk-****")

        # 只改 base_url → model 与密钥保持不变
        r = c.put("/api/settings", json={"llm": {"base_url": "https://x.example/v2"}})
        assert r.status_code == 200
        got = r.json()["llm"]
        assert got["base_url"] == "https://x.example/v2"
        assert got["model"] == "m1"
        assert got["api_key"] and got["api_key"].startswith("sk-****")

        # 只换密钥 → 地址与模型保持不变
        r = c.put("/api/settings", json={"llm": {"api_key": "sk-QAnew9998765432"}})
        assert r.status_code == 200
        got = r.json()["llm"]
        assert got["base_url"] == "https://x.example/v2" and got["model"] == "m1"
        assert got["api_key"].endswith("432") and got["api_key"].startswith("sk-****")

        # 提交掩码 → 按"未修改"处理，不回写、不清除
        r = c.put("/api/settings", json={"llm": {"model": "m2", "api_key": got["api_key"]}})
        assert r.status_code == 200
        got = r.json()["llm"]
        assert got["model"] == "m2"
        assert got["api_key"].endswith("432") and got["api_key"].startswith("sk-****")

        # 显式置 null → 清除（仅清该字段）
        r = c.put("/api/settings", json={"llm": {"api_key": None}})
        assert r.status_code == 200
        got = r.json()["llm"]
        assert got["api_key"] is None
        assert got["base_url"] == "https://x.example/v2" and got["model"] == "m2"


def test_origin_guard() -> None:
    with _client() as c:
        r = c.get("/api/studies", headers={"Origin": "http://evil.example"})
        assert r.status_code == 403
        r2 = c.get("/api/studies", headers={"Origin": "http://localhost:5173"})
        assert r2.status_code == 200
