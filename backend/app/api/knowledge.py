"""技能树与结构编辑 API（B2、B5-01、接口设计 §3）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas import (
    ExcludeBody,
    ExcludeImpact,
    KnowledgeNode,
    KnowledgeTree,
    KpMutationResult,
    OutlineEventItem,
    OutlineStatus,
    RenameBody,
    RestorePreview,
    RestoreResult,
)
from app.services import knowledge, outline

router = APIRouter(tags=["knowledge"])


@router.get("/studies/{study_id}/knowledge", response_model=KnowledgeTree)
def knowledge_tree(study_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    return knowledge.knowledge_tree(db, study_id)


@router.get("/studies/{study_id}/outline-status", response_model=OutlineStatus)
def outline_status(study_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    from app.core.errors import NotFound
    from app.models import Study

    study = db.get(Study, study_id)
    if study is None:
        raise NotFound("学习项目不存在")
    return outline.outline_status_dto(db, study)


@router.get("/studies/{study_id}/outline/events", response_model=list[OutlineEventItem])
def outline_events(
    study_id: int, limit: int = 50, db: Session = Depends(get_db)
) -> list[dict[str, object]]:
    return knowledge.outline_events(db, study_id, limit=limit)


@router.get("/studies/{study_id}/outline/restore-preview", response_model=RestorePreview)
def restore_preview(study_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    return knowledge.restore_original_preview(db, study_id)


@router.post("/studies/{study_id}/outline/restore-original", response_model=RestoreResult)
def restore_original(study_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    return knowledge.restore_original(db, study_id)


@router.get("/kps/{kp_id}/exclude-impact", response_model=ExcludeImpact)
def exclude_impact(kp_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    return knowledge.exclude_impact(db, kp_id)


@router.patch("/kps/{kp_id}", response_model=KnowledgeNode)
def rename_kp(kp_id: int, body: RenameBody, db: Session = Depends(get_db)) -> dict[str, object]:
    from app.services.tree_core import TreeIndex

    kp = knowledge.rename(db, kp_id, body.name)
    index = TreeIndex(db, kp.study_id)
    return knowledge._node_dto(db, index, kp)


@router.post("/kps/{kp_id}/exclude", response_model=KpMutationResult)
def exclude_kp(
    kp_id: int, body: ExcludeBody, db: Session = Depends(get_db)
) -> dict[str, object]:
    return knowledge.exclude(db, kp_id, body.reason)


@router.post("/kps/{kp_id}/restore", response_model=KpMutationResult)
def restore_kp(kp_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    return knowledge.restore(db, kp_id)


@router.post("/kps/{kp_id}/dissolve-group", response_model=KpMutationResult)
def dissolve_group(kp_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    return knowledge.dissolve_group(db, kp_id)
