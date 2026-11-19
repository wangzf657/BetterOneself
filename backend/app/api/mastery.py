"""掌握档案(M6-02/03)、学习报告导出(M6-04)、全量导出(M7-03)。"""

from collections.abc import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    Card,
    KnowledgePoint,
    MasteryEvent,
    Plan,
    Quiz,
    ReviewLog,
    Source,
    Study,
    Task,
)
from app.services import studies

router = APIRouter(prefix="/api", tags=["mastery"])


@router.get("/studies/{study_id}/mastery")
def mastery_view(study_id: int, db: Session = Depends(get_db)) -> dict:
    """档案视图(M6-02/03):知识点+系统评估+自评并列,证据链可查。"""
    kps = db.scalars(
        select(KnowledgePoint)
        .where(KnowledgePoint.study_id == study_id)
        .order_by(KnowledgePoint.sort_order, KnowledgePoint.id)
    ).fetchall()
    events = db.scalars(
        select(MasteryEvent)
        .where(MasteryEvent.kp_id.in_([kp.id for kp in kps]))
        .order_by(MasteryEvent.id)
    ).fetchall() if kps else []
    by_kp: dict[int, list[dict]] = {}
    for e in events:
        by_kp.setdefault(e.kp_id, []).append(
            {
                "id": e.id,
                "from_status": e.from_status,
                "to_status": e.to_status,
                "evidence_type": e.evidence_type,
                "evidence_id": e.evidence_id,
                "created_at": e.created_at.isoformat(),
            }
        )
    return {
        "kps": [
            {
                "id": kp.id,
                "parent_id": kp.parent_id,
                "name": kp.name,
                "kp_type": kp.kp_type,
                "mastery_status": kp.mastery_status,
                "self_reported": kp.self_reported,
                "events": by_kp.get(kp.id, []),
            }
            for kp in kps
        ]
    }


def _report_md(db: Session, study_id: int) -> str:
    study = studies.get_study(db, study_id)
    kps = db.scalars(
        select(KnowledgePoint)
        .where(KnowledgePoint.study_id == study_id)
        .order_by(KnowledgePoint.sort_order, KnowledgePoint.id)
    ).fetchall()
    tasks_done = db.scalars(
        select(Task).where(Task.study_id == study_id, Task.status == "done")
    ).fetchall()
    minutes = sum(t.estimated_minutes for t in tasks_done)
    cards = db.scalars(select(Card).where(Card.study_id == study_id)).fetchall()
    card_ids = [c.id for c in cards]
    logs = (
        db.scalars(select(ReviewLog).where(ReviewLog.card_id.in_(card_ids))).fetchall()
        if card_ids
        else []
    )
    retention = (
        sum(1 for c in cards if c.stability and c.stability >= 1) / len(cards) if cards else 0
    )
    lines = [
        f"# 学习报告:{study.name if study else study_id}",
        "",
        f"> 目标:{study.goal if study else '-'}",
        "",
        "## 知识点清单与掌握状态",
        "",
        "| 知识点 | 类型 | 系统评估 | 自评 |",
        "|---|---|---|---|",
    ]
    for kp in kps:
        lines.append(
            f"| {kp.name} | {kp.kp_type} | {kp.mastery_status} | {kp.self_reported} |"
        )
    lines += [
        "",
        "## 统计",
        "",
        f"- 完成任务:{len(tasks_done)} 个(预估学习时长 {minutes} 分钟)",
        f"- 卡片留存:{len(cards)} 张,其中稳定卡片 {retention:.0%};复习 {len(logs)} 次",
        "",
    ]
    return "\n".join(lines)


@router.get("/studies/{study_id}/report.md")
def report(study_id: int, db: Session = Depends(get_db)) -> StreamingResponse:
    """结项学习报告(M6-04):Markdown 下载。"""
    content = _report_md(db, study_id)

    def iter_bytes() -> Iterator[bytes]:
        yield content.encode("utf-8")

    return StreamingResponse(
        iter_bytes(),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=report-{study_id}.md"},
    )


@router.get("/export")
def export_all(db: Session = Depends(get_db)) -> StreamingResponse:
    """全量数据导出(M7-03):所有业务表 JSON,可再导入或被第三方读取。"""
    import json

    def dump(model, order_by):
        rows = db.scalars(select(model).order_by(order_by)).fetchall()
        return [
            {
                c.name: str(getattr(r, c.name))
                if hasattr(getattr(r, c.name), "isoformat")
                else getattr(r, c.name)
                for c in model.__table__.columns
            }
            for r in rows
        ]

    payload = {
        "studies": dump(Study, Study.id),
        "sources": dump(Source, Source.id),
        "knowledge_points": dump(KnowledgePoint, KnowledgePoint.id),
        "plans": dump(Plan, Plan.id),
        "tasks": dump(Task, Task.id),
        "quizzes": dump(Quiz, Quiz.id),
        "cards": dump(Card, Card.id),
        "review_logs": dump(ReviewLog, ReviewLog.id),
        "mastery_events": dump(MasteryEvent, MasteryEvent.id),
    }

    def iter_bytes() -> Iterator[bytes]:
        yield json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

    return StreamingResponse(
        iter_bytes(),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=betteroneself-export.json"},
    )
