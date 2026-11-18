"""M4-01/02/03:到期队列、四档评分、FSRS 排程与参数可见。"""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine, utcnow
from app.models import Card, ReviewLog, Setting
from tests.util import setup_study_with_kp


def _make_cards(client, n=3) -> list[dict]:
    ctx = setup_study_with_kp(client)
    cards = []
    for i in range(n):
        c = client.post(
            f"/api/studies/{ctx['study']['id']}/cards",
            json={"kp_id": ctx["kp"]["id"], "front": f"卡{i}", "back_md": "背"},
        )
        assert c.status_code == 201
        cards.append(c.json())
    return cards


def test_new_cards_due_immediately_in_queue(client):
    cards = _make_cards(client, 3)
    study_id = cards[0]["study_id"]
    queue = client.get("/api/review/queue", params={"study_id": study_id}).json()
    assert [c["id"] for c in queue] == [c["id"] for c in cards]
    assert all(c["state"] == "Learning" for c in queue)


def test_queue_daily_limit(client):
    ctx = setup_study_with_kp(client)
    with Session(get_engine()) as db:
        db.merge(Setting(id=1, daily_review_limit=2))
        db.commit()
    for i in range(5):
        client.post(
            f"/api/studies/{ctx['study']['id']}/cards",
            json={"kp_id": ctx["kp"]["id"], "front": f"c{i}", "back_md": "b"},
        )
    queue = client.get("/api/review/queue").json()
    assert len(queue) == 2  # 每日上限(M4-01)


def test_rating_changes_interval_and_logs(client):
    cards = _make_cards(client, 1)
    card = cards[0]

    resp = client.post(f"/api/cards/{card['id']}/rate", json={"rating": 3})
    assert resp.status_code == 200
    good = resp.json()
    assert good["due"] > card["due"]  # 评分后进入新排程
    assert good["stability"] is not None
    assert good["last_review_at"] is not None

    # 相邻两次复习间隔随评分变化(M4-03):轻松的稳定度 > 困难
    hard = client.post(f"/api/cards/{card['id']}/rate", json={"rating": 2}).json()
    with Session(get_engine()) as db:
        row = db.get(Card, card["id"])
        row.due = utcnow() - timedelta(minutes=1)  # 拉回到期便于连续评分
        db.commit()
    easy = client.post(f"/api/cards/{card['id']}/rate", json={"rating": 4}).json()
    assert easy["stability"] > hard["stability"]

    with Session(get_engine()) as db:
        logs = db.scalars(select(ReviewLog)).fetchall()
    assert [log.rating for log in logs] == [3, 2, 4]


def test_again_requeues_same_day(client):
    cards = _make_cards(client, 1)
    card = cards[0]
    resp = client.post(f"/api/cards/{card['id']}/rate", json={"rating": 1})
    due_dt = datetime.fromisoformat(resp.json()["due"].replace("Z", "+00:00"))
    # "忘了"当日重现(M4-02):到期仍在今天,且最多 10 分钟后即可再次出队
    assert due_dt.date() == utcnow().date()
    assert due_dt <= utcnow() + timedelta(minutes=10)


def test_fsrs_params_visible(client):
    resp = client.get("/api/review/params")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["parameters"]) >= 17  # 排程参数可查看(M4-03)
    assert 0 < body["desired_retention"] <= 1
