"""计划与任务(M2-04/05/06, M5-01/02)。

排程规则:
- 只排叶子知识点(结构父节点是分组不占任务);依赖拓扑排序,绝不"先学依赖方"
- 按每日时长上限装箱;晚于期限给明确 warning(M2-05)
- 重排=改 scheduled_date 不换行(数据模型 3.3);保上限顺延完成日并留痕 plan_events
- 今日页惰性触发逾期重排(技术总纲 2.4,不上常驻调度)
"""

import json
from datetime import date, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import today
from app.models import Plan, PlanEvent, Task
from app.services import knowledge

# 每知识点预估学习时长(分钟),按类型;无更细依据前不做内容长度估计
ESTIMATE = {"concept": 25, "fact": 15, "procedure": 40}
DEFAULT_DEADLINE_DAYS = 30
DEFAULT_DAILY_MINUTES = 45


def topo_order(
    kps: list, deps: list[tuple[int, int]]
) -> list:
    """Kahn 拓扑排序;同层按 (sort_order, id) 稳定。"""
    indegree = {kp.id: 0 for kp in kps}
    out_edges: dict[int, list[int]] = {}
    for kp_id, dep_id in deps:
        indegree[kp_id] += 1
        out_edges.setdefault(dep_id, []).append(kp_id)

    by_id = {kp.id: kp for kp in kps}
    ready = sorted(
        [kp for kp in kps if indegree[kp.id] == 0], key=lambda k: (k.sort_order, k.id)
    )
    ordered: list = []
    while ready:
        kp = ready.pop(0)
        ordered.append(kp)
        for nxt in out_edges.get(kp.id, []):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(by_id[nxt])
                ready.sort(key=lambda k: (k.sort_order, k.id))
    # 成环残余(理论上落库时已防)按稳定序追加,保证不丢知识点
    remainder = [kp for kp in kps if kp not in ordered]
    return ordered + remainder


def fit_days(order: list, start: date, daily_minutes: int) -> tuple[dict[int, date], date]:
    """按每日上限装箱,返回 kp_id→日期与实际结束日。"""
    assignment: dict[int, date] = {}
    cur, used = start, 0
    for kp in order:
        est = ESTIMATE.get(kp.kp_type, 25)
        if used > 0 and used + est > daily_minutes:
            cur += timedelta(days=1)
            used = 0
        assignment[kp.id] = cur
        used += est
    return assignment, cur


def generate_plan(
    db: Session,
    study_id: int,
    *,
    goal_depth: str = "",
    deadline: date | None = None,
    daily_minutes: int = DEFAULT_DAILY_MINUTES,
    skipped: bool = False,
) -> tuple[Plan, str | None]:
    """访谈三问 → 生成计划草案(M2-04/05)。替换旧 draft。"""
    db.execute(
        delete(Task).where(
            Task.plan_id.in_(
                select(Plan.id).where(Plan.study_id == study_id, Plan.status == "draft")
            )
        )
    )
    db.execute(
        delete(PlanEvent).where(
            PlanEvent.plan_id.in_(
                select(Plan.id).where(Plan.study_id == study_id, Plan.status == "draft")
            )
        )
    )
    db.execute(delete(Plan).where(Plan.study_id == study_id, Plan.status == "draft"))

    if skipped:
        goal_depth = "标准理解(跳过访谈的默认值)"
        deadline = today() + timedelta(days=DEFAULT_DEADLINE_DAYS)
        daily_minutes = DEFAULT_DAILY_MINUTES

    plan = Plan(
        study_id=study_id,
        status="draft",
        goal_depth=goal_depth,
        deadline=deadline,
        daily_minutes=daily_minutes,
    )
    db.add(plan)
    db.flush()

    leaves, deps = knowledge.load_leaves_with_deps(db, study_id)
    assignment, end_date = fit_days(topo_order(leaves, deps), today(), daily_minutes)
    for kp_id, day in assignment.items():
        db.add(
            Task(
                plan_id=plan.id,
                study_id=study_id,
                kp_id=kp_id,
                task_type="learn",
                scheduled_date=day,
                estimated_minutes=ESTIMATE.get(
                    next(k.kp_type for k in leaves if k.id == kp_id), 25
                ),
            )
        )

    warning = None
    if deadline and end_date > deadline:
        warning = (
            f"按每日 {daily_minutes} 分钟,计划将在 {end_date.isoformat()} 完成,"
            f"晚于期限 {deadline.isoformat()}。可提高每日时长、延后期限,或精简知识点。"
        )
    db.add(
        PlanEvent(
            plan_id=plan.id,
            event_type="generated",
            detail_json=json.dumps(
                {
                    "kp_count": len(assignment),
                    "start": today().isoformat(),
                    "end": end_date.isoformat(),
                    "skipped": skipped,
                    "warning": warning,
                },
                ensure_ascii=False,
            ),
        )
    )
    db.commit()
    db.refresh(plan)
    return plan, warning


def get_current_plan(db: Session, study_id: int) -> Plan | None:
    return db.scalar(
        select(Plan)
        .where(Plan.study_id == study_id, Plan.status.in_(["draft", "active"]))
        .order_by(Plan.id.desc())
    )


def list_tasks(db: Session, plan_id: int) -> list[Task]:
    return list(
        db.scalars(
            select(Task).where(Task.plan_id == plan_id).order_by(Task.scheduled_date, Task.id)
        )
    )


def list_events(db: Session, plan_id: int) -> list[PlanEvent]:
    return list(
        db.scalars(
            select(PlanEvent).where(PlanEvent.plan_id == plan_id).order_by(PlanEvent.id)
        )
    )


def confirm_plan(db: Session, plan: Plan) -> Plan:
    """计划确认生效(M2-06):旧 active 归档。"""
    for old in db.scalars(
        select(Plan).where(Plan.study_id == plan.study_id, Plan.status == "active")
    ).fetchall():
        old.status = "archived"
    plan.status = "active"
    db.add(PlanEvent(plan_id=plan.id, event_type="confirmed", detail_json="{}"))
    db.commit()
    db.refresh(plan)
    return plan


def _refit(db: Session, plan: Plan, skip_ids: set[int] | None = None) -> None:
    """重排该计划 pending 任务:保持原相对顺序,从今天起重新装箱(M2-06/M5-02)。

    skip_ids:用户手动移动的任务固定不动,只重排其余任务(M2-06 移动语义)。
    """
    pending = list(
        db.scalars(
            select(Task)
            .where(Task.plan_id == plan.id, Task.status == "pending")
            .order_by(Task.scheduled_date, Task.id)
        )
    )
    if skip_ids:
        pending = [t for t in pending if t.id not in skip_ids]
    if not pending:
        return
    cur, used = today(), 0
    for task in pending:
        if used > 0 and used + task.estimated_minutes > plan.daily_minutes:
            cur += timedelta(days=1)
            used = 0
        task.scheduled_date = cur
        used += task.estimated_minutes


def move_task(db: Session, task: Task, new_date: date) -> Task:
    """移动单日任务到其他日;其余任务围绕重算,被移动任务固定(M2-06)。

    shortcut: 其余任务与被移动任务同日可能超出每日上限,未做跨日避让;计划页出现超载警示时升级
    """
    task.scheduled_date = new_date
    db.add(
        PlanEvent(
            plan_id=task.plan_id,
            event_type="adjusted",
            detail_json=json.dumps(
                {"task_id": task.id, "date": new_date.isoformat()}, ensure_ascii=False
            ),
        )
    )
    plan = db.get(Plan, task.plan_id)
    if plan is not None:
        _refit(db, plan, skip_ids={task.id})
    db.commit()
    db.refresh(task)
    return task


def reschedule_overdue(db: Session, study_id: int | None = None) -> list[dict]:
    """逾期自动重排(M5-02):pending 且 date < today 的任务移入未来日程,不堆积。

    返回重排明细(前端"以下任务已重排"横幅数据)。
    """
    stmt = select(Task).where(Task.status == "pending", Task.scheduled_date < today())
    if study_id is not None:
        stmt = stmt.where(Task.study_id == study_id)
    overdue = list(db.scalars(stmt.order_by(Task.scheduled_date, Task.id)))
    if not overdue:
        return []

    before = {t.id: t.scheduled_date for t in overdue}
    overdue_ids = {t.id for t in overdue}

    # 逐计划 first-fit 装箱:只搬逾期任务,不动的未逾期任务占用的每日容量必须保留
    # (M5-02 重排不堆积;此前全量 _refit 会把未逾期任务连同挪动,破坏次日针对性任务)
    for plan in {db.get(Plan, t.plan_id) for t in overdue}:
        if plan is None:
            continue
        others = [
            t
            for t in db.scalars(
                select(Task).where(
                    Task.plan_id == plan.id,
                    Task.status == "pending",
                    Task.scheduled_date >= today(),
                )
            )
            if t.id not in overdue_ids
        ]
        day_used: dict[date, int] = {}
        for t in others:
            day_used[t.scheduled_date] = day_used.get(t.scheduled_date, 0) + t.estimated_minutes
        for t in sorted(overdue, key=lambda x: (x.scheduled_date, x.id)):
            if t.plan_id != plan.id:
                continue
            day = today()
            while (
                day_used.get(day, 0) + t.estimated_minutes > plan.daily_minutes
                and day_used.get(day, 0) > 0
            ):
                day += timedelta(days=1)
            t.scheduled_date = day
            day_used[day] = day_used.get(day, 0) + t.estimated_minutes

    moved = [
        {
            "task_id": t.id,
            "kp_id": t.kp_id,
            "from": before[t.id].isoformat(),
            "to": t.scheduled_date.isoformat(),
        }
        for t in overdue
        if t.scheduled_date != before[t.id]
    ]
    if moved:
        plans_moved = {db.get(Plan, t.plan_id) for t in overdue}
        for plan in plans_moved:
            if plan is not None:
                db.add(
                    PlanEvent(
                        plan_id=plan.id,
                        event_type="rescheduled",
                        detail_json=json.dumps({"tasks": moved}, ensure_ascii=False),
                    )
                )
    db.commit()
    return moved


def today_view(db: Session, study_id: int | None = None) -> dict:
    """今日任务聚合(M3-01/M5-01):打开即执行逾期重排(惰性触发),再取当日任务。"""
    rescheduled = reschedule_overdue(db, study_id)

    stmt = select(Task).where(Task.status == "pending", Task.scheduled_date == today())
    if study_id is not None:
        stmt = stmt.where(Task.study_id == study_id)
    tasks = list(db.scalars(stmt.order_by(Task.id)))

    from app.services import review as review_svc

    plan_stmt = select(Plan.id).where(Plan.status.in_(["draft", "active"]))
    if study_id is not None:
        plan_stmt = plan_stmt.where(Plan.study_id == study_id)
    return {
        "date": today().isoformat(),
        "has_plan": db.scalar(plan_stmt) is not None,
        "tasks": [
            {
                "id": t.id,
                "plan_id": t.plan_id,
                "study_id": t.study_id,
                "kp_id": t.kp_id,
                "kp_name": _kp_name(db, t.kp_id) or "",
                "task_type": t.task_type,
                "estimated_minutes": t.estimated_minutes,
                "status": t.status,
                "scheduled_date": t.scheduled_date,
                "weak_evidence_id": t.weak_evidence_id,
            }
            for t in tasks
        ],
        "rescheduled": rescheduled,
        "due_reviews": len(review_svc.get_queue(db, study_id)),
    }


def _kp_name(db: Session, kp_id: int) -> str | None:
    from app.models import KnowledgePoint

    kp = db.get(KnowledgePoint, kp_id)
    return kp.name if kp else None
