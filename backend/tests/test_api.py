"""API 集成冒烟（TestClient）：路由、错误码、SSE、跨书保护。"""

from __future__ import annotations

import io
from contextlib import asynccontextmanager

from fastapi.testclient import TestClient

from tests.conftest import BOOK


def _client() -> TestClient:
    from app.main import create_app

    app = create_app()

    @asynccontextmanager
    async def noop_lifespan(app):
        yield  # 测试已自行建库，跳过迁移与启动恢复

    app.router.lifespan_context = noop_lifespan  # type: ignore[assignment]
    return TestClient(app, base_url="http://127.0.0.1:8000")


def _create_book(c: TestClient, name: str = "API 书") -> dict:
    r = c.post(
        "/api/studies",
        data={"name": name},
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


def test_knowledge_tree_and_outline_status() -> None:
    with _client() as c:
        sid = _create_book(c)["id"]
        tree = c.get(f"/api/studies/{sid}/knowledge").json()
        assert tree["progress"]["total"] >= 5
        assert all("status" in n for n in tree["nodes"])

        status = c.get(f"/api/studies/{sid}/outline-status").json()
        assert status["status"] in ("idle", "skipped", "ready", "failed", "planning")

        events = c.get(f"/api/studies/{sid}/outline/events").json()
        assert any(e["event_type"] == "structure_built" for e in events)


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
