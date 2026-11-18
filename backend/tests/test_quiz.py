"""M3-04/05 + M6-01:出题、判分、错题沉淀卡片、掌握状态与证据链。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import MasteryEvent, Quiz
from tests.util import setup_study_with_kp


def _setup(client) -> dict:
    ctx = setup_study_with_kp(client)
    session = client.post(
        f"/api/studies/{ctx['study']['id']}/sessions", json={"kp_id": ctx["kp"]["id"]}
    ).json()
    ctx["session"] = session
    return ctx


def _answer_of(client, quiz_id: int) -> str:
    with Session(get_engine()) as db:
        return db.get(Quiz, quiz_id).answer


def test_generate_quizzes_shape(client):
    ctx = _setup(client)
    resp = client.post(f"/api/sessions/{ctx['session']['id']}/quizzes")
    assert resp.status_code == 201
    quizzes = resp.json()
    assert len(quizzes) == 3
    types = [q["q_type"] for q in quizzes]
    assert types.count("objective") == 2 and types.count("short_answer") == 1
    # 未作答不泄露答案
    assert all("answer" not in q for q in quizzes)
    obj = next(q for q in quizzes if q["q_type"] == "objective")
    assert len(obj["options"]) == 4


def test_objective_grading_and_wrong_answer_creates_card(client):
    ctx = _setup(client)
    quizzes = client.post(f"/api/sessions/{ctx['session']['id']}/quizzes").json()
    obj = next(q for q in quizzes if q["q_type"] == "objective")

    # 答错(选干扰项)→ is_correct False + 自动生成卡片
    right = _answer_of(client, obj["id"])
    wrong = next(o for o in obj["options"] if o != right)
    resp = client.post(f"/api/quizzes/{obj['id']}/answer", json={"answer": wrong})
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_correct"] is False
    assert body["answer"]  # 判分后回传答案

    cards = client.get(f"/api/studies/{ctx['study']['id']}/cards").json()
    assert len(cards) == 1
    card = cards[0]
    assert card["front"] == obj["question"]
    assert card["origin"] == "auto_quiz"
    assert card["kp_id"] == ctx["kp"]["id"]
    assert "来源" in card["back_md"]  # 背面含源引用(M3-05)

    # 重复作答 409
    dup = client.post(f"/api/quizzes/{obj['id']}/answer", json={"answer": wrong})
    assert dup.status_code == 409


def test_objective_correct_grading(client):
    ctx = _setup(client)
    quizzes = client.post(f"/api/sessions/{ctx['session']['id']}/quizzes").json()
    obj = next(q for q in quizzes if q["q_type"] == "objective")
    resp = client.post(
        f"/api/quizzes/{obj['id']}/answer", json={"answer": f"  {_answer_of(client, obj['id'])}  "}
    )
    assert resp.json()["is_correct"] is True


def test_short_answer_ai_grading(client):
    ctx = _setup(client)
    quizzes = client.post(f"/api/sessions/{ctx['session']['id']}/quizzes").json()
    short = next(q for q in quizzes if q["q_type"] == "short_answer")

    resp = client.post(f"/api/quizzes/{short['id']}/answer", json={"answer": "完全无关的答案"})
    body = resp.json()
    assert body["is_correct"] is False
    assert body["ai_feedback"]  # 简答由 AI 评分并给评语(M3-04)


def test_mastery_state_and_evidence_chain(client):
    ctx = _setup(client)

    def kp_status() -> str:
        tree = client.get(f"/api/studies/{ctx['study']['id']}/knowledge").json()

        def find(nodes):
            for n in nodes:
                if n["name"] == "移动语义":
                    return n
                hit = find(n["children"])
                if hit:
                    return hit

        return find(tree)["mastery_status"]

    quizzes = client.post(f"/api/sessions/{ctx['session']['id']}/quizzes").json()
    assert kp_status() == "new"

    # 第一题答错:new→learning,证据链留痕
    right = _answer_of(client, quizzes[0]["id"])
    client.post(f"/api/quizzes/{quizzes[0]['id']}/answer", json={"answer": right + "错"})
    assert kp_status() == "learning"
    with Session(get_engine()) as db:
        events = db.scalars(select(MasteryEvent)).fetchall()
    assert events[-1].from_status == "new" and events[-1].to_status == "learning"
    assert events[-1].evidence_type == "quiz"

    # 后两题连续答对 → passed(每题取各自的正确答案)
    client.post(
        f"/api/quizzes/{quizzes[1]['id']}/answer",
        json={"answer": _answer_of(client, quizzes[1]["id"])},
    )
    client.post(
        f"/api/quizzes/{quizzes[2]['id']}/answer",
        json={"answer": "移动语义的核心是赋值即移动,原变量随后不可用,这避免了重复分配。"},
    )
    assert kp_status() == "passed"

    with Session(get_engine()) as db:
        last = db.scalars(select(MasteryEvent)).fetchall()[-1]
    assert last.to_status == "passed"
    assert last.evidence_id  # "已通过"可追溯到具体测验


def test_manual_card_creation(client):
    ctx = _setup(client)
    resp = client.post(
        f"/api/studies/{ctx['study']['id']}/cards",
        json={"kp_id": ctx["kp"]["id"], "front": "什么是借用?", "back_md": "引用不拥有值"},
    )
    assert resp.status_code == 201
    assert resp.json()["origin"] == "manual_mark"
