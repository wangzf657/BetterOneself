"""掌握档案(M6-01):状态由测验证据驱动,每次变更写入 mastery_events 证据链。

规则:任何作答 new→learning;连续 2 次答对 learning→passed("已通过"必须有测验通过证据)。
薄弱(weak)判定在 M4-05(连续 2 次错)接入。
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KnowledgePoint, MasteryEvent, Quiz


def record_quiz_result(db: Session, quiz: Quiz) -> None:
    kp = db.get(KnowledgePoint, quiz.kp_id)
    if kp is None:
        return

    if kp.mastery_status == "new":
        _transition(db, kp, "learning", quiz)

    answered = [
        q
        for q in db.scalars(
            select(Quiz).where(Quiz.kp_id == kp.id, Quiz.is_correct.is_not(None)).order_by(Quiz.id)
        )
    ]
    if (
        quiz.is_correct
        and kp.mastery_status == "learning"
        and len(answered) >= 2
        and all(q.is_correct for q in answered[-2:])
    ):
        _transition(db, kp, "passed", quiz)


def _transition(db: Session, kp: KnowledgePoint, to_status: str, quiz: Quiz) -> None:
    db.add(
        MasteryEvent(
            kp_id=kp.id,
            from_status=kp.mastery_status,
            to_status=to_status,
            evidence_type="quiz",
            evidence_id=str(quiz.id),
        )
    )
    kp.mastery_status = to_status
    db.commit()
