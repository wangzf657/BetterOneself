"""复习系统(M3-05, M4-01/02/03):py-fsrs 排程、到期队列、四档评分。不自研排程。"""

import json
from datetime import UTC, timedelta

from fsrs import Card as FsrsCard
from fsrs import Rating, Scheduler, State
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import Card as CardRow
from app.models import ReviewLog, Setting

# "忘了"当日重现的上限间隔(M4-02);FSRS 学习期本身给出分钟级间隔,这里是兜底
_AGAIN_MAX_DELAY = timedelta(minutes=10)


def _scheduler(db: Session) -> Scheduler:
    row = db.get(Setting, 1)
    if row and row.fsrs_params_json:
        return Scheduler(parameters=json.loads(row.fsrs_params_json))
    return Scheduler()


def fsrs_params(db: Session) -> dict:
    s = _scheduler(db)
    return {"parameters": list(s.parameters), "desired_retention": s.desired_retention}


def _to_fsrs(card: CardRow) -> FsrsCard:
    # py-fsrs 强制 aware UTC;库内为 naive UTC,边界转换
    due = card.due or utcnow()
    return FsrsCard(
        state=State[card.state] if card.state else State.Learning,
        step=0,
        stability=card.stability,
        difficulty=card.difficulty,
        due=due.replace(tzinfo=UTC),
        last_review=(
            card.last_review_at.replace(tzinfo=UTC) if card.last_review_at else None
        ),
    )


def create_card(
    db: Session,
    study_id: int,
    kp_id: int,
    front: str,
    back_md: str,
    chunk_id: int | None = None,
    origin: str = "manual_new",
) -> CardRow:
    f = FsrsCard()  # 新卡:due=now, 学习态
    due = f.due.replace(tzinfo=None) if f.due.tzinfo else f.due
    card = CardRow(
        study_id=study_id,
        kp_id=kp_id,
        front=front,
        back_md=back_md,
        chunk_id=chunk_id,
        origin=origin,
        due=due,
        state=f.state.name if f.state else None,
        stability=f.stability,
        difficulty=f.difficulty,
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    return card


def get_queue(db: Session, study_id: int | None = None) -> list[CardRow]:
    """到期卡按紧迫排序出队,数量上限默认 20 可调(M4-01)。"""
    setting = db.get(Setting, 1)
    limit = setting.daily_review_limit if setting else 20
    stmt = (
        select(CardRow)
        .where(CardRow.status == "active", CardRow.due <= utcnow())
        .order_by(CardRow.due)
        .limit(limit)
    )
    if study_id is not None:
        stmt = stmt.where(CardRow.study_id == study_id)
    return list(db.scalars(stmt))


def rate_card(db: Session, card: CardRow, rating: int) -> CardRow:
    """四档评分驱动下次到期(M4-02/03);评分即落 ReviewLog 证据。"""
    now = utcnow()
    reviewed, _log = _scheduler(db).review_card(
        _to_fsrs(card), Rating(rating), review_datetime=now.replace(tzinfo=UTC)
    )
    due = reviewed.due.replace(tzinfo=None)
    if rating == 1:  # 忘了:保证当日队列内重现
        due = min(due, now + _AGAIN_MAX_DELAY)
    elapsed = (now - card.last_review_at).days if card.last_review_at else 0
    card.due = due
    card.stability = reviewed.stability
    card.difficulty = reviewed.difficulty
    card.state = reviewed.state.name if reviewed.state else None
    card.last_review_at = now
    db.add(
        ReviewLog(
            card_id=card.id,
            rating=rating,
            scheduled_days=max((due - now).total_seconds() / 86400, 0),
            elapsed_days=elapsed,
        )
    )
    db.commit()
    db.refresh(card)
    return card
