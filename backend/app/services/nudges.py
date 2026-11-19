"""督促(M5-03/05/06):每日摘要、周复盘、中断回炉。惰性触发,文案用模板(V1.0 从简)。"""

import json
from datetime import date, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import today
from app.db import utcnow
from app.models import (
    Card,
    KnowledgePoint,
    Plan,
    ReviewLog,
    Setting,
    Summary,
    Task,
)


def _day_metrics(db: Session, study_id: int, day: date) -> dict:
    day_start = day
    day_end = day + timedelta(days=1)
    tasks_done = db.scalar(
        select(func.count(Task.id)).where(
            Task.study_id == study_id,
            Task.status == "done",
            Task.completed_at >= day_start.isoformat(),
            Task.completed_at < day_end.isoformat(),
        )
    ) or 0
    reviews = db.scalar(
        select(func.count(ReviewLog.id)).where(
            ReviewLog.reviewed_at >= day_start.isoformat(),
            ReviewLog.reviewed_at < day_end.isoformat(),
            ReviewLog.card_id.in_(select(Card.id).where(Card.study_id == study_id)),
        )
    ) or 0
    due = len(
        db.scalars(
            select(Card.id).where(
                Card.study_id == study_id,
                Card.status == "active",
                Card.due <= utcnow(),
            )
        ).fetchall()
    )
    kps_passed = db.scalar(
        select(func.count(KnowledgePoint.id)).where(
            KnowledgePoint.study_id == study_id, KnowledgePoint.mastery_status == "passed"
        )
    ) or 0
    return {"tasks_done": tasks_done, "reviews": reviews, "due": due, "kps_passed": kps_passed}


def ensure_daily_summary(db: Session, study_id: int) -> Summary | None:
    """当日摘要(M5-03):有学习行为才生成;当日已生成则返回已有。"""
    day = today()
    existing = db.scalar(
        select(Summary).where(
            Summary.study_id == study_id,
            Summary.summary_type == "daily",
            Summary.period_date == day,
        )
    )
    if existing is not None:
        return existing
    metrics = _day_metrics(db, study_id, day)
    if metrics["tasks_done"] == 0 and metrics["reviews"] == 0:
        return None  # 无当日学习行为,不生成(M5-03 验收)
    tomorrow_tasks = list(
        db.scalars(
            select(Task)
            .where(
                Task.study_id == study_id,
                Task.status == "pending",
                Task.scheduled_date == day + timedelta(days=1),
            )
            .order_by(Task.id)
        )
    )
    kp_names = [_kp_name(db, t.kp_id) for t in tomorrow_tasks]
    lines = [
        f"# 今日摘要 {day.isoformat()}",
        "",
        f"- 完成任务:{metrics['tasks_done']} 个",
        f"- 复习卡片:{metrics['reviews']} 次",
        f"- 当前到期未清:{metrics['due']} 张",
        f"- 累计已通过知识点:{metrics['kps_passed']} 个",
        "",
        "## 明日预告",
    ]
    lines += [f"- {name or '知识点'}" for name in kp_names] or ["- 无"]
    summary = Summary(
        study_id=study_id,
        summary_type="daily",
        period_date=day,
        content_md="\n".join(lines),
        metrics_json=json.dumps(metrics, ensure_ascii=False),
    )
    db.add(summary)
    db.commit()
    db.refresh(summary)
    return summary


def ensure_weekly_review(db: Session, study_id: int) -> Summary:
    """周复盘(M5-05):本周一以来无 weekly 则生成;建议需用户确认,不自动改计划。"""
    day = today()
    monday = day - timedelta(days=day.weekday())
    existing = db.scalar(
        select(Summary).where(
            Summary.study_id == study_id,
            Summary.summary_type == "weekly",
            Summary.period_date == monday,
        )
    )
    if existing is not None:
        return existing

    week_end = day + timedelta(days=1)
    tasks_total = db.scalar(
        select(func.count(Task.id)).where(
            Task.study_id == study_id,
            Task.scheduled_date >= monday,
            Task.scheduled_date < week_end,
            Task.status != "skipped",
        )
    ) or 0
    tasks_done = db.scalar(
        select(func.count(Task.id)).where(
            Task.study_id == study_id,
            Task.scheduled_date >= monday,
            Task.scheduled_date < week_end,
            Task.status == "done",
        )
    ) or 0
    passed = db.scalar(
        select(func.count(KnowledgePoint.id)).where(
            KnowledgePoint.study_id == study_id, KnowledgePoint.mastery_status == "passed"
        )
    ) or 0
    weak = db.scalar(
        select(func.count(KnowledgePoint.id)).where(
            KnowledgePoint.study_id == study_id, KnowledgePoint.mastery_status == "weak"
        )
    ) or 0

    rate = f"{tasks_done}/{tasks_total}" if tasks_total else "0/0"
    if tasks_total == 0:
        completion_line = "本周无数据——没有安排任何任务。"
    elif tasks_total and tasks_done / tasks_total < 0.3:
        completion_line = f"完成率偏低({rate})。建议下调每日时长或减少知识点,让计划回到可完成。"
    else:
        completion_line = f"完成率 {rate},节奏健康。"

    lines = [
        f"# 周复盘(自 {monday.isoformat()})",
        "",
        f"- 任务完成:{completion_line}",
        f"- 掌握进展:已通过 {passed} 个知识点,薄弱 {weak} 个",
    ]
    if weak:
        lines.append(f"- 遗忘预警:有 {weak} 个薄弱知识点,建议优先针对性复习(已自动插入次日任务)")
    lines.append("")
    lines.append("以上建议仅供参考;确认后才调整计划(可到计划页手动调整)。")
    summary = Summary(
        study_id=study_id,
        summary_type="weekly",
        period_date=monday,
        content_md="\n".join(lines),
        metrics_json=json.dumps(
            {"tasks_total": tasks_total, "tasks_done": tasks_done, "passed": passed, "weak": weak},
            ensure_ascii=False,
        ),
    )
    db.add(summary)
    db.commit()
    db.refresh(summary)
    return summary


def check_inactivity(db: Session, study_id: int) -> dict:
    """中断检测(M5-06):最近一次学习行为距今 N 天(默认 5)→ 建议回炉。"""
    setting = _setting_row(db)
    threshold = setting.inactivity_threshold_days if setting else 5
    last = _last_activity(db, study_id)
    if last is None:
        return {"inactive_days": 0, "suggest_reset": False}
    last_day = last.date() if isinstance(last, datetime) else last
    days = (today() - last_day).days
    return {"inactive_days": days, "suggest_reset": days >= threshold}


def return_from_break(db: Session, study_id: int) -> dict:
    """回炉(M5-06):重排全部剩余任务到今天起;薄弱知识点的卡片提到今天到期。"""
    plan = db.scalar(select(Plan).where(Plan.study_id == study_id, Plan.status == "active"))
    moved = 0
    if plan is not None:
        pending = list(
            db.scalars(
                select(Task)
                .where(Task.plan_id == plan.id, Task.status == "pending")
                .order_by(Task.scheduled_date, Task.id)
            )
        )
        cur, used = today(), 0
        for t in pending:
            if used > 0 and used + t.estimated_minutes > plan.daily_minutes:
                cur += timedelta(days=1)
                used = 0
            t.scheduled_date = cur
            used += t.estimated_minutes
        moved = len(pending)

    weak_kp_ids = set(
        db.scalars(
            select(KnowledgePoint.id).where(
                KnowledgePoint.study_id == study_id, KnowledgePoint.mastery_status == "weak"
            )
        )
    )
    cards_pulled = 0
    if weak_kp_ids:
        result = db.execute(
            update(Card)
            .where(Card.kp_id.in_(weak_kp_ids), Card.status == "active")
            .values(due=utcnow())
        )
        rowcount = getattr(result, "rowcount", 0)
        cards_pulled = rowcount or 0
    db.commit()
    return {"tasks_rescheduled": moved, "weak_cards_pulled": cards_pulled}


def _setting_row(db: Session) -> Setting | None:
    return db.get(Setting, 1)


def _as_date(value) -> date:
    return value.date() if isinstance(value, datetime) else value


def _last_activity(db: Session, study_id: int):
    """最近学习行为日期:任务完成 / 复习 / 会话开始 的最大值(只到日期粒度)。"""
    from app.models import LearningSession

    latest: date | None = None
    for dt in db.scalars(
        select(Task.completed_at).where(
            Task.study_id == study_id, Task.status == "done", Task.completed_at.is_not(None)
        )
    ):
        d = _as_date(dt)
        latest = d if latest is None or d > latest else latest
    for dt in db.scalars(
        select(ReviewLog.reviewed_at).where(
            ReviewLog.card_id.in_(select(Card.id).where(Card.study_id == study_id))
        )
    ):
        d = _as_date(dt)
        latest = d if latest is None or d > latest else latest
    stmt = select(LearningSession.started_at).where(LearningSession.study_id == study_id)
    for dt in db.scalars(stmt):
        d = _as_date(dt)
        latest = d if latest is None or d > latest else latest
    return latest


def _kp_name(db: Session, kp_id: int) -> str | None:
    kp = db.get(KnowledgePoint, kp_id)
    return kp.name if kp else None
