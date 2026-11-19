"""掌握档案(M6-01, M4-05):状态由证据驱动,每次变更写入 mastery_events。

统一证据流(时间序):quiz(is_correct)与 review(rating=1 视为错)混合排列。
- 连续 2 条错误证据 → weak,并触发次日 review_weak 任务(M5-04)
- weak 后任一次 quiz 答对 → learning(再连续 2 对 → passed,恢复通道)
"""

from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import today
from app.models import (
    KnowledgePoint,
    MasteryEvent,
    Plan,
    Quiz,
    ReviewLog,
    Task,
)


def record_quiz_result(db: Session, quiz: Quiz) -> None:
    kp = db.get(KnowledgePoint, quiz.kp_id)
    if kp is None:
        return
    if kp.mastery_status == "new":
        _transition(db, kp, "learning", "quiz", str(quiz.id))
    if quiz.is_correct:
        _maybe_pass(db, kp)
    else:
        _maybe_weak(db, kp, "quiz", str(quiz.id))


def record_review_result(db: Session, kp_id: int, review_log_id: int, rating: int) -> None:
    """复习"忘了"(rating=1)也进入弱点证据流(M4-05)。"""
    kp = db.get(KnowledgePoint, kp_id)
    if kp is None:
        return
    if rating == 1:
        _maybe_weak(db, kp, "review", str(review_log_id))


def _maybe_pass(db: Session, kp: KnowledgePoint) -> None:
    if kp.mastery_status == "weak":
        # 薄弱恢复通道:一次答对即回 learning,后续仍可冲 passed
        _transition(db, kp, "learning", "quiz", None)
    if kp.mastery_status != "learning":
        return
    answered = list(
        db.scalars(
            select(Quiz)
            .where(Quiz.kp_id == kp.id, Quiz.is_correct.is_not(None))
            .order_by(Quiz.id)
        )
    )
    if len(answered) >= 2 and all(q.is_correct for q in answered[-2:]):
        _transition(db, kp, "passed", "quiz", str(answered[-1].id))


def _maybe_weak(db: Session, kp: KnowledgePoint, evidence_type: str, evidence_id: str) -> None:
    """最近 2 条证据(quiz/review 混合时间序)都错 → weak(M4-05)。"""
    from app.models import Card

    events: list[dict[str, Any]] = [
        {"correct": bool(q.is_correct), "type": "quiz", "id": q.id}
        for q in db.scalars(select(Quiz).where(Quiz.kp_id == kp.id, Quiz.is_correct.is_not(None)))
    ] + [
        {"correct": log.rating != 1, "type": "review", "id": log.id}
        for log in db.scalars(
            select(ReviewLog).where(
                ReviewLog.card_id.in_(select(Card.id).where(Card.kp_id == kp.id))
            )
        )
    ]
    events.sort(key=lambda e: e["id"])
    if len(events) >= 2 and not events[-1]["correct"] and not events[-2]["correct"]:
        if kp.mastery_status != "weak":
            event = _transition(db, kp, "weak", evidence_type, evidence_id)
            _spawn_review_weak_task(db, kp, event)


def _transition(
    db: Session,
    kp: KnowledgePoint,
    to_status: str,
    evidence_type: str,
    evidence_id: str | None,
) -> MasteryEvent:
    event = MasteryEvent(
        kp_id=kp.id,
        from_status=kp.mastery_status,
        to_status=to_status,
        evidence_type=evidence_type,
        evidence_id=evidence_id or "",
    )
    db.add(event)
    db.flush()
    kp.mastery_status = to_status
    db.commit()
    return event


def _spawn_review_weak_task(db: Session, kp: KnowledgePoint, event: MasteryEvent) -> None:
    """薄弱点 → 次日针对性任务(M5-04),挂在 active 计划上。"""
    plan = db.scalar(
        select(Plan).where(Plan.study_id == kp.study_id, Plan.status == "active")
    )
    if plan is None:
        return  # 无计划(纯浏览/复习阶段)无处挂任务;薄弱点已在档案可见
    if any(
        t.task_type == "review_weak"
        and t.weak_evidence_id == str(event.id)
        for t in db.scalars(select(Task).where(Task.plan_id == plan.id, Task.kp_id == kp.id))
    ):
        return  # 同一证据不重复插
    db.add(
        Task(
            plan_id=plan.id,
            study_id=kp.study_id,
            kp_id=kp.id,
            task_type="review_weak",
            scheduled_date=today() + timedelta(days=1),
            estimated_minutes=15,
            weak_evidence_id=str(event.id),
        )
    )
    db.commit()
