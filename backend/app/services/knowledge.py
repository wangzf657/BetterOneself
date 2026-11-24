"""知识骨架服务（B2、B5-01）：树、进度、重命名、排除/恢复、解散分组、恢复原目录。"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound, Validation
from app.models import KnowledgePoint, OutlineEvent, Quiz, Study
from app.services.events import record_event
from app.services.outline import supersede_pending
from app.services.tree_core import TreeIndex, evidence_kp_ids


def _kp_or_404(db: Session, kp_id: int) -> KnowledgePoint:
    kp = db.get(KnowledgePoint, kp_id)
    if kp is None:
        raise NotFound("节点不存在")
    return kp


def _node_dto(db: Session, index: TreeIndex, kp: KnowledgePoint) -> dict[str, Any]:
    status = index.status_of(kp)
    lighted_count, valid_total = index.subtree_progress(kp.id)
    recent_quiz = (
        db.query(Quiz)
        .filter(Quiz.kp_id == kp.id, Quiz.answered_at.is_not(None))
        .order_by(Quiz.answered_at.desc())
        .first()
    )
    recent: dict[str, Any] | None = None
    if recent_quiz is not None and recent_quiz.grading_results_json:
        recent = {
            "quiz_id": recent_quiz.id,
            "passed": recent_quiz.passed,
            "correct_count": recent_quiz.correct_count,
            "pass_line": recent_quiz.pass_line,
            "answered_at": recent_quiz.answered_at,
        }
    return {
        "id": kp.id,
        "name": kp.name,
        "sort_order": kp.sort_order,
        "parent_id": kp.parent_id,
        "is_chapter": kp.is_chapter,
        "is_learning_unit": kp.id in index.valid_units,
        "origin": kp.origin,
        "confidence": kp.confidence,
        "confidence_basis": kp.confidence_basis,
        "planning_note": kp.planning_note,
        "excluded": kp.excluded,
        "exclusion_reason": kp.exclusion_reason,
        "status": status,
        "lighted_at": kp.lighted_at,
        "lighted_by_quiz_id": kp.lighted_by_quiz_id,
        "lighted_count": lighted_count if index.children.get(kp.id) else None,
        "valid_total": valid_total if index.children.get(kp.id) else None,
        "recent_quiz": recent,
        "children": [
            _node_dto(db, index, c) for c in index.children.get(kp.id, [])
        ],
    }


def knowledge_tree(db: Session, study_id: int) -> dict[str, Any]:
    study = db.get(Study, study_id)
    if study is None:
        raise NotFound("学习项目不存在")
    index = TreeIndex(db, study_id)
    roots = index.children.get(None, [])
    progress = index.progress()
    return {
        "study_id": study_id,
        "progress": progress.as_dict() if progress.total else None,
        "nodes": [_node_dto(db, index, kp) for kp in roots],
    }


def rename(db: Session, kp_id: int, name: str) -> KnowledgePoint:
    kp = _kp_or_404(db, kp_id)
    name = name.strip()
    if not name or len(name) > 200:
        raise Validation("节点名长度需在 1–200 字之间")
    old = kp.name
    if old == name:
        return kp
    kp.name = name
    record_event(
        db, kp.study_id, "kp_renamed", "user", kp_id=kp.id,
        detail={"before": old, "after": name}, kp_name=name,
    )
    db.commit()  # 重命名不改变分母、不写分母事件（B5-01）
    return kp


def exclude_impact(db: Session, kp_id: int) -> dict[str, Any]:
    """排除影响预览：不落库，实时计算（P1-01）。"""
    kp = _kp_or_404(db, kp_id)
    before_index = TreeIndex(db, kp.study_id)
    before = before_index.progress()
    after_index = TreeIndex(db, kp.study_id, excluded_extra={kp.id})
    after = after_index.progress()
    subtree = before_index.subtree_ids(kp.id)
    lighted_affected = sum(
        1
        for i in subtree
        if i in before_index.valid_units and before_index.by_id[i].lighted_at is not None
    )
    return {
        "kp_id": kp.id,
        "kp_name": kp.name,
        "lighted_affected": lighted_affected,
        "progress_before": before.as_dict() if before.total else None,
        "progress_after": after.as_dict() if after.total else None,
    }


def exclude(db: Session, kp_id: int, reason: str | None) -> dict[str, Any]:
    kp = _kp_or_404(db, kp_id)
    if kp.excluded:
        raise Conflict("该节点已排除")
    before_index = TreeIndex(db, kp.study_id)
    before = before_index.progress()
    kp.excluded = True
    kp.exclusion_reason = (reason or None)
    record_event(
        db, kp.study_id, "kp_excluded", "user", kp_id=kp.id,
        detail={
            "reason": reason,
            "progress_before": before.as_dict() if before.total else None,
            "progress_after": None,  # 提交后回填
        },
        kp_name=kp.name,
    )
    db.flush()
    after_index = TreeIndex(db, kp.study_id, excluded_extra={kp.id})
    after = after_index.progress()
    _patch_last_event(db, kp.study_id, "progress_after",
                      after.as_dict() if after.total else None)
    db.commit()
    return {
        "kp": _node_dto(db, TreeIndex(db, kp.study_id), kp),
        "progress_before": before.as_dict() if before.total else None,
        "progress_after": after.as_dict() if after.total else None,
    }


def restore(db: Session, kp_id: int) -> dict[str, Any]:
    kp = _kp_or_404(db, kp_id)
    if not kp.excluded:
        raise Conflict("该节点未被排除")
    before_index = TreeIndex(db, kp.study_id)
    before = before_index.progress()
    kp.excluded = False
    kp.exclusion_reason = None
    record_event(
        db, kp.study_id, "kp_restored", "user", kp_id=kp.id,
        detail={"progress_before": before.as_dict() if before.total else None},
        kp_name=kp.name,
    )
    db.flush()
    after_index = TreeIndex(db, kp.study_id, excluded_removed={kp.id})
    after = after_index.progress()
    _patch_last_event(db, kp.study_id, "progress_after",
                      after.as_dict() if after.total else None)
    db.commit()
    return {
        "kp": _node_dto(db, TreeIndex(db, kp.study_id), kp),
        "progress_before": before.as_dict() if before.total else None,
        "progress_after": after.as_dict() if after.total else None,
    }


def _patch_last_event(db: Session, study_id: int, key: str, value: Any) -> None:
    event = (
        db.query(OutlineEvent)
        .filter(OutlineEvent.study_id == study_id)
        .order_by(OutlineEvent.id.desc())
        .first()
    )
    if event is not None and event.detail_json:
        detail = json.loads(event.detail_json)
        detail[key] = value
        event.detail_json = json.dumps(detail, ensure_ascii=False)


def dissolve_group(db: Session, kp_id: int) -> dict[str, Any]:
    kp = _kp_or_404(db, kp_id)
    if kp.origin != "ai_group":
        raise Validation("仅 AI 部分分组可以解散")
    index = TreeIndex(db, kp.study_id)
    before = index.progress()
    children = index.children.get(kp.id, [])
    if not children:
        raise Validation("该分组没有子章")
    for i, child in enumerate(children, start=kp.sort_order):
        child.parent_id = kp.parent_id
        child.sort_order = i
    group_name = kp.name
    db.delete(kp)
    record_event(
        db, kp.study_id, "group_dissolved", "user",
        detail={"group": group_name,
                "chapters": [c.name for c in children],
                "progress_before": before.as_dict() if before.total else None},
        kp_name=group_name,
    )
    db.flush()
    _renumber_siblings(db, kp.parent_id)
    after_index = TreeIndex(db, kp.study_id)
    after = after_index.progress()
    _patch_last_event(db, kp.study_id, "progress_after",
                      after.as_dict() if after.total else None)
    db.commit()
    first_child = children[0]
    return {
        "kp": _node_dto(db, TreeIndex(db, kp.study_id), first_child),
        "progress_before": before.as_dict() if before.total else None,
        "progress_after": after.as_dict() if after.total else None,
    }


def _renumber_siblings(db: Session, parent_id: int | None) -> None:
    kids = (
        db.query(KnowledgePoint)
        .filter(
            KnowledgePoint.parent_id == parent_id
            if parent_id is not None
            else KnowledgePoint.parent_id.is_(None)
        )
        .order_by(KnowledgePoint.sort_order, KnowledgePoint.id)
        .all()
    )
    for i, kid in enumerate(kids, start=1):
        kid.sort_order = i


def outline_events(db: Session, study_id: int, limit: int = 50) -> list[dict[str, Any]]:
    events = (
        db.query(OutlineEvent)
        .filter(OutlineEvent.study_id == study_id)
        .order_by(OutlineEvent.id.desc())
        .limit(limit)
        .all()
    )
    out: list[dict[str, Any]] = []
    for e in events:
        detail: dict[str, Any] = {}
        if e.detail_json:
            try:
                detail = json.loads(e.detail_json)
            except json.JSONDecodeError:
                detail = {}
        out.append(
            {
                "id": e.id,
                "event_type": e.event_type,
                "actor": e.actor,
                "kp_id": e.kp_id,
                "kp_name": detail.pop("kp_name", None),
                "detail": detail,
                "created_at": e.created_at,
            }
        )
    return out


def restore_original_preview(db: Session, study_id: int) -> dict[str, Any]:
    """恢复原目录前置预览（撤销清单）。"""
    study = db.get(Study, study_id)
    if study is None:
        raise NotFound("学习项目不存在")
    ai_ops = _count_events(db, study_id, {"kp_created", "kp_excluded"}, actor="ai")
    renames = _count_events(db, study_id, {"kp_renamed"})
    exclusions = _count_events(db, study_id, {"kp_excluded"}, actor="user")
    evidence = evidence_kp_ids(db, study_id)
    return {
        "can_restore": not evidence and study.outline_status != "planning",
        "planning_running": study.outline_status == "planning",
        "evidence_kps": [_name_of(db, i) for i in sorted(evidence)],
        "ai_adjustments": ai_ops,
        "revoked_renames": renames,
        "revoked_exclusions": exclusions,
    }


def _name_of(db: Session, kp_id: int) -> str:
    kp = db.get(KnowledgePoint, kp_id)
    return kp.name if kp else f"#{kp_id}"


def _count_events(
    db: Session, study_id: int, types: set[str], *, actor: str | None = None
) -> int:
    q = db.query(OutlineEvent).filter(
        OutlineEvent.study_id == study_id, OutlineEvent.event_type.in_(types)
    )
    if actor:
        q = q.filter(OutlineEvent.actor == actor)
    return q.count()


def restore_original(db: Session, study_id: int) -> dict[str, Any]:
    """以 structure_built 快照重建（决策 #29）：前置=全书无学习证据且非 planning。"""
    study = db.get(Study, study_id)
    if study is None:
        raise NotFound("学习项目不存在")
    if study.outline_status == "planning":
        raise Conflict("AI 规划正在进行中，不能恢复原目录")
    evidence = evidence_kp_ids(db, study_id)
    if evidence:
        raise Validation(
            "这本书已有学习证据（会话/测验/笔记/点亮），不能整体恢复；请改用逐个排除",
        )
    snapshot_event = (
        db.query(OutlineEvent)
        .filter(OutlineEvent.study_id == study_id, OutlineEvent.event_type == "structure_built")
        .order_by(OutlineEvent.id.desc())
        .first()
    )
    if snapshot_event is None or not snapshot_event.detail_json:
        raise Validation("没有可用的原始结构快照")
    snapshot = json.loads(snapshot_event.detail_json)

    index = TreeIndex(db, study_id)
    before = index.progress()

    revoked_renames = _count_events(db, study_id, {"kp_renamed"})
    revoked_exclusions = _count_events(db, study_id, {"kp_excluded"}, actor="user")
    ai_ops = _count_events(db, study_id, {"kp_created", "kp_excluded"}, actor="ai")

    supersede_pending(db, study_id)  # 待确认的建议对着将被重置的树，一并作废

    # 快照节点带稳定 ID：先清空现树，再按快照重建（含 refs 映射）
    db.query(KnowledgePoint).filter(KnowledgePoint.study_id == study_id).delete()
    db.flush()
    removed = 0
    for node in snapshot.get("nodes", []):
        db.add(
            KnowledgePoint(
                id=node["id"],
                study_id=study_id,
                parent_id=node.get("parent_id"),
                name=node["name"],
                sort_order=node["sort_order"],
                is_chapter=node.get("is_chapter", False),
                origin=node.get("origin", "toc"),
                confidence=node.get("confidence", 0.7),
                confidence_basis=node.get("confidence_basis", "标题规则识别"),
                excluded=False,
            )
        )
        removed += 1
    db.flush()
    from app.models import KnowledgeRef

    refs = snapshot.get("refs", {})
    for kp_id_str, chunk_ids in refs.items():
        for cid in chunk_ids:
            db.add(
                KnowledgeRef(
                    kp_id=int(kp_id_str), chunk_id=int(cid), sort_order=int(cid)
                )
            )
    study.outline_thesis = None
    study.outline_status = "skipped"
    study.outline_error = "已恢复原目录；可重新进行 AI 规划"
    record_event(
        db,
        study_id,
        "outline_restored",
        "user",
        detail={
            "removed": removed,
            "restored": len(snapshot.get("nodes", [])),
            "revoked_renames": revoked_renames,
            "revoked_exclusions": revoked_exclusions,
            "ai_adjustments": ai_ops,
        },
    )
    db.flush()
    after_index = TreeIndex(db, study_id)
    after = after_index.progress()
    _patch_last_event(
        db, study_id, "progress_after", after.as_dict() if after.total else None
    )
    db.commit()
    return {
        "removed": removed,
        "restored": len(snapshot.get("nodes", [])),
        "ai_adjustments": ai_ops,
        "revoked_renames": revoked_renames,
        "revoked_exclusions": revoked_exclusions,
        "progress_before": before.as_dict() if before.total else None,
        "progress_after": after.as_dict() if after.total else None,
    }


__all__ = [
    "dissolve_group",
    "exclude",
    "exclude_impact",
    "knowledge_tree",
    "outline_events",
    "rename",
    "restore",
    "restore_original",
    "restore_original_preview",
]
