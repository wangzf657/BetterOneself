"""M2-04/05/06 + M5-01/02:计划生成/确认/调整/逾期重排/今日聚合。"""

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import Task
from tests.util import setup_study_with_kp

TODAY = date(2026, 11, 18)


def _with_today(client, monkeypatch, day: str):
    """把 config 的 fake_today 设为指定日期(E2E 同款机制)。"""
    from app import config

    config.get_config.cache_clear()
    monkeypatch.setenv("BO_FAKE_TODAY", day)
    # 重新读配置(清缓存后由 env 重建)


def _plan(client, study_id, **kw):
    payload = {
        "goal_depth": "能写 CLI",
        "deadline": (TODAY + timedelta(days=7)).isoformat(),
        "daily_minutes": 45,
        **kw,
    }
    resp = client.post(f"/api/studies/{study_id}/plans", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_generate_plan_follows_dependency_order(client, monkeypatch):
    _with_today(client, monkeypatch, TODAY.isoformat())
    ctx = setup_study_with_kp(client)

    plan = _plan(client, ctx["study"]["id"])
    tasks = plan["tasks"]
    assert len(tasks) >= 2  # 移动语义 + 借用 两个叶子
    # stub 依赖推断:同列表顺序链式(借用 依赖 移动语义)→ 不出现先学依赖方
    by_kp = {t["kp_name"]: t for t in tasks}
    if "移动语义" in by_kp and "借用" in by_kp:
        assert by_kp["移动语义"]["scheduled_date"] <= by_kp["借用"]["scheduled_date"]
    # 起始日 = 今天
    assert all(t["scheduled_date"] >= TODAY.isoformat() for t in tasks)


def test_generate_plan_daily_cap_and_warning(client, monkeypatch):
    _with_today(client, monkeypatch, TODAY.isoformat())
    ctx = setup_study_with_kp(client)

    # 每日 20 分钟:concept 25min 一天只能装一个 → 任务跨多日
    plan = _plan(client, ctx["study"]["id"], daily_minutes=20)
    days = {t["scheduled_date"] for t in plan["tasks"]}
    assert len(days) >= 2  # 超上限时拆到多日

    # 期限给到当天但任务装不完 → 明确 warning
    tight = _plan(client, ctx["study"]["id"], deadline=TODAY.isoformat())
    assert tight["warning"] and "晚于期限" in tight["warning"]


def test_skip_interview_uses_defaults_and_marks(client, monkeypatch):
    _with_today(client, monkeypatch, TODAY.isoformat())
    ctx = setup_study_with_kp(client)
    plan = _plan(client, ctx["study"]["id"], skipped=True)
    assert plan["goal_depth"].startswith("标准理解")
    assert plan["deadline"] == (TODAY + timedelta(days=30)).isoformat()
    gen = next(e for e in plan["events"] if e["event_type"] == "generated")
    import json

    assert json.loads(gen["detail_json"])["skipped"] is True


def test_confirm_and_move_task_recalculates(client, monkeypatch):
    _with_today(client, monkeypatch, TODAY.isoformat())
    ctx = setup_study_with_kp(client)
    plan = _plan(client, ctx["study"]["id"])

    confirmed = client.post(f"/api/plans/{plan['id']}/confirm").json()
    assert confirmed["status"] == "active"

    first = confirmed["tasks"][0]
    moved = client.patch(
        f"/api/tasks/{first['id']}",
        json={"scheduled_date": (TODAY + timedelta(days=5)).isoformat()},
    ).json()
    assert moved["scheduled_date"] == (TODAY + timedelta(days=5)).isoformat()
    # 调整后即时重算后续安排:仍在计划内且不早于今天
    after = client.get(f"/api/studies/{ctx['study']['id']}/plan").json()
    assert all(t["scheduled_date"] >= TODAY.isoformat() for t in after["tasks"])
    # 调整留痕
    assert any(e["event_type"] == "adjusted" for e in after["events"])


def test_overdue_rescheduled_on_today_view(client, monkeypatch):
    ctx = setup_study_with_kp(client)
    _with_today(client, monkeypatch, TODAY.isoformat())
    plan = _plan(client, ctx["study"]["id"])
    client.post(f"/api/plans/{plan['id']}/confirm")

    # 时间推进 5 天:原任务全部逾期
    _with_today(client, monkeypatch, (TODAY + timedelta(days=5)).isoformat())
    view = client.get("/api/today").json()
    # 逾期任务被重排进未来,今日任务从今天开始
    moved = view["rescheduled"]
    assert moved, "逾期任务应被重排"
    assert all(m["to"] >= (TODAY + timedelta(days=5)).isoformat() for m in moved)
    # 重排 = 改日期不换行:任务 id 不变,仍属同一计划
    with Session(get_engine()) as db:
        task = db.get(Task, moved[0]["task_id"])
        assert task is not None and task.status == "pending"
    detail = client.get(f"/api/studies/{ctx['study']['id']}/plan").json()
    assert any(e["event_type"] == "rescheduled" for e in detail["events"])
    # 无堆积:不存在 date < today 的 pending
    assert all(
        t["scheduled_date"] >= (TODAY + timedelta(days=5)).isoformat() for t in detail["tasks"]
    )


def test_today_view_shape(client, monkeypatch):
    _with_today(client, monkeypatch, TODAY.isoformat())
    ctx = setup_study_with_kp(client)
    plan = _plan(client, ctx["study"]["id"])
    client.post(f"/api/plans/{plan['id']}/confirm")

    view = client.get("/api/today").json()
    assert view["date"] == TODAY.isoformat()
    assert len(view["tasks"]) >= 1
    assert view["tasks"][0]["kp_name"]
    assert "due_reviews" in view


def test_complete_task(client, monkeypatch):
    _with_today(client, monkeypatch, TODAY.isoformat())
    ctx = setup_study_with_kp(client)
    plan = _plan(client, ctx["study"]["id"])
    client.post(f"/api/plans/{plan['id']}/confirm")
    first = plan["tasks"][0]
    done = client.post(f"/api/tasks/{first['id']}/complete").json()
    assert done["status"] == "done"
