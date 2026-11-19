"""M4-05 + M5-04:薄弱点判定(连错×2)、次日针对性任务、恢复通道。"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import today
from app.db import get_engine
from app.models import MasteryEvent, Task
from tests.util import setup_study_with_kp

TODAY = today()


def _plan_and_session(client):
    ctx = setup_study_with_kp(client)
    client.post(
        f"/api/studies/{ctx['study']['id']}/plans",
        json={"goal_depth": "d", "daily_minutes": 45, "skipped": False},
    )
    plan = client.get(f"/api/studies/{ctx['study']['id']}/plan").json()
    client.post(f"/api/plans/{plan['id']}/confirm")
    session = client.post(
        f"/api/studies/{ctx['study']['id']}/sessions", json={"kp_id": ctx["kp"]["id"]}
    ).json()
    ctx["session"] = session
    return ctx


def _quizzes(client, ctx):
    return client.post(f"/api/sessions/{ctx['session']['id']}/quizzes").json()


def _answer(client, quiz_id, correct_text_fn, correct: bool):
    from sqlalchemy.orm import Session as S

    from app.db import get_engine
    from app.models import Quiz

    with S(get_engine()) as db:
        answer = db.get(Quiz, quiz_id).answer
    text = answer if correct else answer + "错误补充"
    return client.post(f"/api/quizzes/{quiz_id}/answer", json={"answer": text}).json()


def _kp_status(client, ctx):
    tree = client.get(f"/api/studies/{ctx['study']['id']}/knowledge").json()

    def find(nodes):
        for n in nodes:
            if n["id"] == ctx["kp"]["id"]:
                return n
            hit = find(n["children"])
            if hit:
                return hit

    return find(tree)["mastery_status"]


def test_two_consecutive_wrong_makes_weak_and_spawns_task(client):
    ctx = _plan_and_session(client)
    quizzes = _quizzes(client, ctx)

    # 第 1 错:new→learning,不弱
    _answer(client, quizzes[0]["id"], None, correct=False)
    assert _kp_status(client, ctx) == "learning"

    # 第 2 错(另一题):→ weak + 次日 review_weak 任务
    _answer(client, quizzes[1]["id"], None, correct=False)
    assert _kp_status(client, ctx) == "weak"

    # 针对性任务(M5-04):明天、带证据、类型 review_weak
    plan = client.get(f"/api/studies/{ctx['study']['id']}/plan").json()
    weak_tasks = [t for t in plan["tasks"] if t["task_type"] == "review_weak"]
    assert len(weak_tasks) == 1
    t = weak_tasks[0]
    assert t["scheduled_date"] == (TODAY + timedelta(days=1)).isoformat()
    assert t["weak_evidence_id"], "必须携带薄弱证据(M5-04)"

    # 证据链可溯:weak 事件的 evidence_id 与任务携带一致
    with Session(get_engine()) as db:
        ev = db.get(MasteryEvent, int(t["weak_evidence_id"]))
        assert ev.to_status == "weak"
        assert ev.from_status == "learning"


def test_wrong_then_right_does_not_make_weak(client):
    ctx = _plan_and_session(client)
    quizzes = _quizzes(client, ctx)
    _answer(client, quizzes[0]["id"], None, correct=False)
    _answer(client, quizzes[1]["id"], None, correct=True)
    assert _kp_status(client, ctx) != "weak"
    plan = client.get(f"/api/studies/{ctx['study']['id']}/plan").json()
    assert not [t for t in plan["tasks"] if t["task_type"] == "review_weak"]


def test_weak_recovers_to_learning_on_correct(client):
    ctx = _plan_and_session(client)
    quizzes = _quizzes(client, ctx)
    _answer(client, quizzes[0]["id"], None, correct=False)
    _answer(client, quizzes[1]["id"], None, correct=False)
    assert _kp_status(client, ctx) == "weak"

    # 针对性复习会话再测验:答对 → 恢复 learning
    s2 = client.post(
        f"/api/studies/{ctx['study']['id']}/sessions", json={"kp_id": ctx["kp"]["id"]}
    ).json()
    q2 = client.post(f"/api/sessions/{s2['id']}/quizzes").json()
    _answer(client, q2[0]["id"], None, correct=True)
    assert _kp_status(client, ctx) == "learning"

    with Session(get_engine()) as db:
        events = db.scalars(select(MasteryEvent).order_by(MasteryEvent.id)).fetchall()
        assert events[-1].to_status == "learning" and events[-1].from_status == "weak"


def test_review_forgot_counts_as_wrong_evidence(client):
    ctx = _plan_and_session(client)
    # 手动建卡并连续两次复习"忘了"(rating=1)
    card = client.post(
        f"/api/studies/{ctx['study']['id']}/cards",
        json={"kp_id": ctx["kp"]["id"], "front": "q", "back_md": "a"},
    ).json()
    client.post(f"/api/cards/{card['id']}/rate", json={"rating": 1})
    # 第二次忘了需等卡片再次到期:直接把 due 拉回

    from sqlalchemy import update

    from app.db import get_engine, utcnow
    from app.models import Card

    with Session(get_engine()) as db:
        db.execute(update(Card).where(Card.id == card["id"]).values(due=utcnow()))
        db.commit()
    client.post(f"/api/cards/{card['id']}/rate", json={"rating": 1})
    assert _kp_status(client, ctx) == "weak"
    plan = client.get(f"/api/studies/{ctx['study']['id']}/plan").json()
    assert len([t for t in plan["tasks"] if t["task_type"] == "review_weak"]) == 1


def test_no_active_plan_still_marks_weak_without_task(client):
    ctx = setup_study_with_kp(client)
    session = client.post(
        f"/api/studies/{ctx['study']['id']}/sessions", json={"kp_id": ctx["kp"]["id"]}
    ).json()
    quizzes = client.post(f"/api/sessions/{session['id']}/quizzes").json()
    _answer(client, quizzes[0]["id"], None, correct=False)
    _answer(client, quizzes[1]["id"], None, correct=False)
    assert _kp_status(client, ctx) == "weak"  # 档案标记不受计划影响
    with Session(get_engine()) as db:
        assert db.scalars(select(Task)).first() is None  # 无计划则无处插任务
