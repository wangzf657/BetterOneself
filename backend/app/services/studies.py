"""学习项目服务（B1、接口设计 §2）。"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from sqlalchemy import text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_config
from app.core.errors import Conflict, NotFound, UnsupportedMedia, Validation
from app.core.security import safe_stored_name, sniff_type
from app.models import KnowledgePoint, Note, Quiz, Session_, Setting, Source, Study
from app.services.tree_core import TreeIndex, evidence_kp_ids

logger = logging.getLogger(__name__)

NAME_MIN, NAME_MAX = 1, 200
SCHEMES = {"guided", "lecture", "drill"}


def _study_or_404(db: Session, study_id: int) -> Study:
    study = db.get(Study, study_id)
    if study is None:
        raise NotFound("学习项目不存在")
    return study


def _source_or_404(db: Session, source_id: int) -> Source:
    source = db.get(Source, source_id)
    if source is None:
        raise NotFound("资料不存在")
    return source


def create_study(
    db: Session,
    *,
    name: str,
    filename: str,
    content: bytes,
    idempotency_key: str | None,
) -> tuple[Study, bool]:
    """返回 (study, created)。幂等键去重（P1-05）；文件落盘不与事务混写（P2-05）。"""
    name = name.strip()
    if not (NAME_MIN <= len(name) <= NAME_MAX):
        raise Validation("书名长度需在 1–200 字之间")
    if idempotency_key:
        existing = (
            db.query(Setting).filter(Setting.key == f"idem.{idempotency_key}").one_or_none()
        )
        if existing is not None:
            study = db.get(Study, int(existing.value or 0))
            if study is not None:
                return study, False

    cfg = get_config()
    if len(content) > cfg.max_upload_bytes:
        raise Validation(f"文件超过大小上限（{cfg.max_upload_bytes // (1024 * 1024)} MB）")
    type_ = sniff_type(filename, content[:16])

    temp_path = cfg.uploads_dir / f"tmp_{uuid.uuid4().hex}.part"
    temp_path.write_bytes(content)
    stored_name = safe_stored_name(type_)

    try:
        study = Study(name=name)
        db.add(study)
        db.flush()
        source = Source(
            study_id=study.id,
            type=type_,
            filename=filename,
            stored_path="",  # 提交后 rename 填回
            size_bytes=len(content),
        )
        db.add(source)
        db.flush()
        study.primary_source_id = source.id
        if idempotency_key:
            db.add(Setting(key=f"idem.{idempotency_key}", value=str(study.id)))
        db.commit()
    except IntegrityError:
        # 并发同键竞态：幂等记录主键冲突 → 回滚后按键返回已有书，仍算幂等命中
        db.rollback()
        temp_path.unlink(missing_ok=True)
        if idempotency_key:
            db.expire_all()
            row = db.get(Setting, f"idem.{idempotency_key}")
            if row is not None:
                study = db.get(Study, int(row.value or 0))
                if study is not None:
                    return study, False
        raise
    except Exception:
        db.rollback()
        temp_path.unlink(missing_ok=True)
        raise
    stored_path = cfg.uploads_dir / stored_name
    temp_path.rename(stored_path)
    source.stored_path = str(stored_path)
    db.commit()
    return study, True


def list_studies(db: Session) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for study in db.query(Study).order_by(Study.created_at.desc()).all():
        source = db.get(Source, study.primary_source_id) if study.primary_source_id else None
        index = TreeIndex(db, study.id)
        progress = index.progress()
        last_kp: dict[str, object] | None = None
        if study.last_kp_id is not None and study.last_kp_id in index.by_id:
            kp = index.by_id[study.last_kp_id]
            status = index.status_of(kp)
            last_kp = {"id": kp.id, "name": kp.name, "status": status}
        out.append(
            {
                "id": study.id,
                "name": study.name,
                "source_id": source.id if source else None,
                "source_type": source.type if source else None,
                "parse_status": source.parse_status if source else None,
                "parse_error": source.parse_error if source else None,
                "outline_status": study.outline_status,
                "progress": progress.as_dict() if progress.total else None,
                "last_learned_at": study.last_learned_at,
                "last_kp": last_kp,
            }
        )
    return out


def get_study(db: Session, study_id: int) -> dict[str, object]:
    study = _study_or_404(db, study_id)
    source = db.get(Source, study.primary_source_id) if study.primary_source_id else None
    return {
        "id": study.id,
        "name": study.name,
        "scheme": study.scheme,
        "outline_thesis": study.outline_thesis,
        "outline_status": study.outline_status,
        "source_type": source.type if source else None,
    }


def patch_study(db: Session, study_id: int, *, name: str | None, scheme: str | None) -> Study:
    study = _study_or_404(db, study_id)
    if name is not None:
        name = name.strip()
        if not (NAME_MIN <= len(name) <= NAME_MAX):
            raise Validation("书名长度需在 1–200 字之间")
        study.name = name
    if scheme is not None:
        if scheme not in SCHEMES:
            raise Validation("学习方法只能是 guided / lecture / drill")
        study.scheme = scheme
    db.commit()
    return study


def delete_impact(db: Session, study_id: int) -> dict[str, int]:
    _study_or_404(db, study_id)
    sessions = db.query(Session_).filter(Session_.study_id == study_id).count()
    quizzes = db.query(Quiz).filter(Quiz.study_id == study_id).count()
    lighted = (
        db.query(KnowledgePoint)
        .filter(KnowledgePoint.study_id == study_id, KnowledgePoint.lighted_at.is_not(None))
        .count()
    )
    notes = db.query(Note).filter(Note.study_id == study_id).count()
    return {"sessions": sessions, "quizzes": quizzes, "lighted": lighted, "notes": notes}


def delete_study(db: Session, study_id: int) -> None:
    """级联清除全部关联；文件清理失败记录错误不静默（数据模型 §7）。"""
    study = _study_or_404(db, study_id)
    stored_paths = [
        s.stored_path
        for s in db.query(Source).filter(Source.study_id == study_id).all()
        if s.stored_path
    ]
    # RESTRICT 列先行清理，避免级联删除顺序问题（lighted_by_quiz_id / refs.chunk_id）
    db.execute(
        text(
            "DELETE FROM vec_chunks WHERE chunk_id IN ("
            " SELECT sc.id FROM source_chunks sc JOIN sources s ON s.id = sc.source_id"
            " WHERE s.study_id = :sid)"
        ),
        {"sid": study_id},
    )
    db.execute(
        text(
            "DELETE FROM knowledge_refs WHERE kp_id IN"
            " (SELECT id FROM knowledge_points WHERE study_id = :sid)"
        ),
        {"sid": study_id},
    )
    db.execute(
        update(KnowledgePoint)
        .where(KnowledgePoint.study_id == study_id)
        .values(lighted_by_quiz_id=None)
    )
    db.delete(study)
    db.commit()
    for p in stored_paths:
        try:
            Path(p).unlink(missing_ok=True)
        except OSError:
            logger.error("删除书籍后清理文件失败：%s", p)


def replace_source(
    db: Session,
    study_id: int,
    *,
    filename: str,
    content: bytes,
) -> Source:
    """更换主文件：仅解析失败且全书无学习证据（P1-05）。"""
    study = _study_or_404(db, study_id)
    source = db.get(Source, study.primary_source_id) if study.primary_source_id else None
    if source is None:
        raise NotFound("该书没有主文件")
    if source.parse_status != "failed":
        raise Conflict("仅解析失败的书可以更换文件")
    if evidence_kp_ids(db, study_id):
        raise Conflict("该书已有学习记录，不能更换文件；可尝试重新解析")

    cfg = get_config()
    if len(content) > cfg.max_upload_bytes:
        raise Validation(f"文件超过大小上限（{cfg.max_upload_bytes // (1024 * 1024)} MB）")
    type_ = sniff_type(filename, content[:16])

    temp_path = cfg.uploads_dir / f"tmp_{uuid.uuid4().hex}.part"
    temp_path.write_bytes(content)
    stored_path = cfg.uploads_dir / safe_stored_name(type_)
    try:
        db.execute(
            text(
                "DELETE FROM vec_chunks WHERE chunk_id IN ("
                " SELECT sc.id FROM source_chunks sc WHERE sc.source_id = :src)"
            ),
            {"src": source.id},
        )
        db.execute(
            text("DELETE FROM knowledge_refs WHERE chunk_id IN"
                 " (SELECT id FROM source_chunks WHERE source_id = :src)"),
            {"src": source.id},
        )
        old_study = study
        db.delete(source)
        db.flush()
        new_source = Source(
            study_id=study_id,
            type=type_,
            filename=filename,
            stored_path="",
            size_bytes=len(content),
        )
        db.add(new_source)
        db.flush()
        old_study.primary_source_id = new_source.id
        db.commit()
    except Exception:
        db.rollback()
        temp_path.unlink(missing_ok=True)
        raise
    temp_path.rename(stored_path)
    new_source.stored_path = str(stored_path)
    db.commit()
    return new_source


def get_source(db: Session, source_id: int) -> Source:
    return _source_or_404(db, source_id)


def source_of_study(db: Session, study_id: int) -> Source | None:
    study = _study_or_404(db, study_id)
    return db.get(Source, study.primary_source_id) if study.primary_source_id else None


__all__ = [
    "UnsupportedMedia",
    "create_study",
    "delete_impact",
    "delete_study",
    "get_source",
    "get_study",
    "list_studies",
    "patch_study",
    "replace_source",
    "source_of_study",
]
