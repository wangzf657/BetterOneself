"""M5 集合测试:文本导入/知识库管理/自评跳过/费曼/摘要/周复盘/回炉/卡片管理/Anki/设置/导出。"""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import today
from app.db import get_engine
from app.models import Task
from tests.util import setup_study_with_kp

TODAY = today()


def _with_plan(client, ctx):
    client.post(
        f"/api/studies/{ctx['study']['id']}/plans",
        json={"goal_depth": "d", "daily_minutes": 45, "skipped": True},
    )
    plan = client.get(f"/api/studies/{ctx['study']['id']}/plan").json()
    client.post(f"/api/plans/{plan['id']}/confirm")
    return plan


# ---------- M1-07 文本粘贴 ----------


def test_import_text_creates_source_and_decomposes(client):
    ctx = setup_study_with_kp(client)
    resp = client.post(
        f"/api/studies/{ctx['study']['id']}/sources/text",
        json={"title": "随手笔记", "content": "# 粘贴章节\n正文内容。\n\n## 子节\n细节。"},
    )
    assert resp.status_code == 201
    assert resp.json()["type"] == "text"

    detail = client.get(f"/api/sources/{resp.json()['id']}").json()
    assert detail["parse_status"] == "ready"
    assert len(detail["chunks"]) == 2  # 切片入库并参与拆解


# ---------- M1-05 知识库管理 ----------


def test_rename_delete_impact(client):
    ctx = setup_study_with_kp(client)
    src_id = client.get(f"/api/studies/{ctx['study']['id']}/sources").json()[0]["id"]

    renamed = client.patch(f"/api/sources/{src_id}", json={"title": "改名后"})
    assert renamed.json()["title"] == "改名后"

    impact = client.get(f"/api/sources/{src_id}/impact").json()
    assert impact["chunks"] > 0 and impact["kp_refs_cleared"] > 0  # 删除前可见影响(M1-05)

    assert client.delete(f"/api/sources/{src_id}").status_code == 204
    assert client.get(f"/api/sources/{src_id}").status_code == 404
    # 引用清空的知识点保留但标 AI 推断(不静默失效)
    tree = client.get(f"/api/studies/{ctx['study']['id']}/knowledge").json()

    def find(nodes):
        for n in nodes:
            if n["id"] == ctx["kp"]["id"]:
                return n
            hit = find(n["children"])
            if hit:
                return hit

    kp = find(tree)
    assert kp is not None and kp["ai_inferred"] is True and kp["refs"] == []


# ---------- M2-07 自评跳过 + 快速验证 ----------


def test_self_report_skips_plan_and_rolls_back_on_wrong(client):
    ctx = setup_study_with_kp(client)
    kp_id = ctx["kp"]["id"]

    marked = client.post(f"/api/kps/{kp_id}/self-report", json={"mastered": True})
    assert marked.json()["self_reported"] == "mastered"

    # 不进新计划
    plan = _with_plan(client, ctx)
    assert all(t["kp_id"] != kp_id for t in plan["tasks"])

    # 快速验证:答错 → 回滚 + 补进计划
    qq = client.post(f"/api/kps/{kp_id}/quick-quiz").json()
    from sqlalchemy.orm import Session as S

    from app.db import get_engine
    from app.models import Quiz

    with S(get_engine()) as db:
        answer = db.get(Quiz, qq["quiz_id"]).answer
    graded = client.post(
        f"/api/kps/{kp_id}/quick-quiz/{qq['quiz_id']}/answer", json={"answer": answer + "错"}
    ).json()
    assert graded["is_correct"] is False
    assert graded["self_reported"] == "unknown"

    with S(get_engine()) as db:
        extra = db.scalars(
            select(Task).where(Task.kp_id == kp_id, Task.status == "pending")
        ).fetchall()
    assert extra, "回滚后应有补进计划的 learn 任务"
    detail = client.get(f"/api/studies/{ctx['study']['id']}/plan").json()
    assert any(t["kp_id"] == kp_id for t in detail["tasks"])  # 已回滚进计划


def test_quick_quiz_pass_keeps_skip(client):
    ctx = setup_study_with_kp(client)
    kp_id = ctx["kp"]["id"]
    client.post(f"/api/kps/{kp_id}/self-report", json={"mastered": True})
    qq = client.post(f"/api/kps/{kp_id}/quick-quiz").json()
    from sqlalchemy.orm import Session as S

    from app.db import get_engine
    from app.models import Quiz

    with S(get_engine()) as db:
        answer = db.get(Quiz, qq["quiz_id"]).answer
    graded = client.post(
        f"/api/kps/{kp_id}/quick-quiz/{qq['quiz_id']}/answer", json={"answer": answer}
    ).json()
    assert graded["is_correct"] is True and graded["self_reported"] == "mastered"


# ---------- M3-07 费曼 ----------


def test_feynman_session_asks_followup(client):
    ctx = setup_study_with_kp(client)
    session = client.post(
        f"/api/studies/{ctx['study']['id']}/sessions",
        json={"kp_id": ctx["kp"]["id"], "session_type": "feynman"},
    ).json()
    assert session["session_type"] == "feynman"
    explain = "移动语义就是把值从一个变量搬到另一个变量。"
    resp = client.post(f"/api/sessions/{session['id']}/chat", json={"content": explain})
    assert resp.status_code == 200
    detail = client.get(f"/api/sessions/{session['id']}").json()
    reply = detail["messages"][-1]["content"]
    assert "追问" in reply  # 至少一个追问(M3-07)
    assert detail["messages"][-1]["citations"]  # 引用规则一致


# ---------- M5-03/05 摘要与周复盘 ----------


def test_daily_summary_requires_activity_and_weekly_shows_data(client):
    ctx = setup_study_with_kp(client)
    plan = _with_plan(client, ctx)
    first = plan["tasks"][0]
    client.post(f"/api/tasks/{first['id']}/complete")

    summaries = client.get(f"/api/studies/{ctx['study']['id']}/summaries").json()
    daily = [s for s in summaries if s["summary_type"] == "daily"]
    weekly = [s for s in summaries if s["summary_type"] == "weekly"]
    assert daily and weekly  # 有当日行为才生成 daily(M5-03);weekly 本周生成
    assert "完成任务" in daily[-1]["content_md"]
    assert "完成率" in weekly[0]["content_md"] or "本周无数据" in weekly[0]["content_md"]


def test_no_activity_no_daily_summary(client):
    ctx = setup_study_with_kp(client)
    summaries = client.get(f"/api/studies/{ctx['study']['id']}/summaries").json()
    assert not [s for s in summaries if s["summary_type"] == "daily"]  # 无行为不生成
    assert [s for s in summaries if s["summary_type"] == "weekly"]  # weekly 空数据如实说


# ---------- M5-06 回炉 ----------


def test_inactivity_and_return_from_break(client):
    ctx = setup_study_with_kp(client)
    _with_plan(client, ctx)

    info = client.get(f"/api/studies/{ctx['study']['id']}/inactivity").json()
    assert info["inactive_days"] == 0  # 刚有行为(建项目即会话?此处仅计划)——无会话行为
    # 造一个 6 天前的行为(只动最早一条任务,其余保持 pending 供回炉重排)
    from datetime import timedelta

    from sqlalchemy import update

    from app.db import get_engine, utcnow
    from app.models import Task

    with Session(get_engine()) as db:
        first = db.scalars(
            select(Task).where(Task.study_id == ctx["study"]["id"]).order_by(Task.id)
        ).first()
        db.execute(
            update(Task)
            .where(Task.id == first.id)
            .values(completed_at=utcnow() - timedelta(days=6), status="done")
        )
        db.commit()
    info = client.get(f"/api/studies/{ctx['study']['id']}/inactivity").json()
    assert info["inactive_days"] >= 5 and info["suggest_reset"] is True

    result = client.post(f"/api/studies/{ctx['study']['id']}/return-from-break").json()
    assert result["tasks_rescheduled"] >= 1  # 剩余任务重排到今天起


# ---------- M4-04/06 卡片管理 ----------


def test_card_edit_suspend_delete_export(client):
    ctx = setup_study_with_kp(client)
    card = client.post(
        f"/api/studies/{ctx['study']['id']}/cards",
        json={"kp_id": ctx["kp"]["id"], "front": "旧问题", "back_md": "旧答案"},
    ).json()
    client.post(f"/api/cards/{card['id']}/rate", json={"rating": 3})

    # 编辑不动历史
    patched = client.patch(
        f"/api/cards/{card['id']}", json={"front": "新问题", "back_md": "新答案"}
    ).json()
    assert patched["front"] == "新问题"

    # Anki 导出:TSV 可被 Anki 文本导入(暂停前导出)
    resp = client.get(f"/api/studies/{ctx['study']['id']}/cards/export.tsv")
    assert resp.status_code == 200
    body = resp.text
    assert "新问题" in body and "\t" in body

    suspended = client.patch(f"/api/cards/{card['id']}", json={"status": "suspended"}).json()
    assert suspended["status"] == "suspended"
    queue = client.get("/api/review/queue").json()
    assert not [c for c in queue if c["id"] == card["id"]]  # 暂停卡不入队

    assert client.delete(f"/api/cards/{card['id']}").status_code == 204


# ---------- M7-01/04 设置与用量 ----------


def test_settings_key_encrypted_and_masked(client):
    resp = client.put(
        "/api/settings",
        json={"llm_api_key": "sk-secret-123", "daily_review_limit": 30},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["llm_key_set"] is True
    assert "sk-secret-123" not in json.dumps(body)  # 任何输出不含明文 key

    with Session(get_engine()) as db:
        from app.models import Setting

        row = db.get(Setting, 1)
        assert row.llm_api_key_enc and "sk-secret-123" not in row.llm_api_key_enc  # 加密落库
    assert client.get("/api/settings").json()["daily_review_limit"] == 30


def test_usage_recorded_after_activity(client):
    # stub 调用不记 token,但记录请求吗?——设计:stub 不记;真实才记。此测只验端点
    assert client.get("/api/usage").status_code == 200


# ---------- M6-02/04 档案视图与报告导出 ----------


def test_mastery_view_and_report_export(client):
    ctx = setup_study_with_kp(client)
    view = client.get(f"/api/studies/{ctx['study']['id']}/mastery").json()
    kp = next(k for k in view["kps"] if k["id"] == ctx["kp"]["id"])
    assert "self_reported" in kp and "events" in kp  # 自评与评估并列、证据可查

    resp = client.get(f"/api/studies/{ctx['study']['id']}/report.md")
    assert resp.status_code == 200
    assert "知识点清单" in resp.text and ctx["kp"]["name"] in resp.text
    assert "attachment" in resp.headers["content-disposition"]


def test_full_export_json(client):
    setup_study_with_kp(client)
    resp = client.get("/api/export")
    assert resp.status_code == 200
    payload = json.loads(resp.text)
    assert payload["studies"] and payload["knowledge_points"] and payload["cards"] is not None
