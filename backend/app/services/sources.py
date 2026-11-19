"""资料管理与解析流水线(M1-02/05/06):上传→后台解析→切片→向量化→ready。"""

import json
import sys
import time
from pathlib import Path

from fastapi import BackgroundTasks
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_config
from app.db import get_engine
from app.ingest import chunker, embedder, parsers, vecstore
from app.models import KnowledgePoint, KnowledgeRef, Source, SourceChunk, StudySource
from app.schemas.source import ChunkOut, SourceDetail

ALLOWED_SUFFIXES = {".pdf": "pdf", ".md": "md", ".markdown": "md"}


def save_upload(db: Session, study_id: int, filename: str, data: bytes) -> Source:
    suffix = Path(filename).suffix.lower()
    kind = ALLOWED_SUFFIXES.get(suffix)
    if kind is None:
        raise ValueError(f"不支持的文件类型: {suffix or '(无后缀)'}")

    # 时间戳前缀防同名覆盖
    raw_path = get_config().uploads_dir / f"{int(time.time() * 1000)}_{Path(filename).name}"
    raw_path.write_bytes(data)

    source = Source(
        title=Path(filename).stem,
        type=kind,
        origin=filename,
        raw_path=str(raw_path),
        parse_status="pending",
    )
    db.add(source)
    db.flush()
    db.add(StudySource(study_id=study_id, source_id=source.id))
    db.commit()
    db.refresh(source)
    return source


def save_text(db: Session, study_id: int, title: str, content: str) -> Source:
    """纯文本粘贴建为资料(M1-07):无 raw_path,内容直接落 content_md。"""
    source = Source(title=title[:300], type="text", origin="粘贴文本",
                    content_md=content, parse_status="pending")
    db.add(source)
    db.flush()
    db.add(StudySource(study_id=study_id, source_id=source.id))
    db.commit()
    db.refresh(source)
    return source


def delete_impact(db: Session, source: Source) -> dict:
    """删除影响预览(M1-05):将清理的切片数与受影响知识点数。"""
    chunk_ids = list(db.scalars(select(SourceChunk.id).where(SourceChunk.source_id == source.id)))
    if not chunk_ids:
        return {"chunks": 0, "kp_refs_cleared": 0}
    kp_refs = db.scalars(
        select(KnowledgeRef).where(KnowledgeRef.chunk_id.in_(chunk_ids))
    ).fetchall()
    return {"chunks": len(chunk_ids), "kp_refs_cleared": len(kp_refs)}


def delete_source(db: Session, source: Source) -> None:
    """删除资料:切片与引用级联清理,引用清空的知识点保留但回退为 AI 推断态。"""
    chunk_ids = list(db.scalars(select(SourceChunk.id).where(SourceChunk.source_id == source.id)))
    if chunk_ids:
        ref_kp_ids = set(
            db.scalars(select(KnowledgeRef.kp_id).where(KnowledgeRef.chunk_id.in_(chunk_ids)))
        )
        for kp_id in ref_kp_ids:
            remaining = db.scalars(
                select(KnowledgeRef.chunk_id).where(
                    KnowledgeRef.kp_id == kp_id,
                    KnowledgeRef.chunk_id.not_in(chunk_ids),
                )
            ).first()
            if remaining is None:
                kp = db.get(KnowledgePoint, kp_id)
                if kp is not None:
                    kp.ai_inferred = True  # 引用清空:不再有来源支撑,明示不静默失效(M1-05)
    db.delete(source)  # chunks/refs/study_sources 由 CASCADE 清理
    db.commit()


def schedule_parse(tasks: BackgroundTasks, source_id: int) -> None:
    tasks.add_task(run_parse, source_id)


def retry_decompose(db: Session, tasks: BackgroundTasks, study_id: int) -> None:
    """拆解重试入口(M1-06):先同步置 running,再后台重跑,前端立即可见状态。"""
    from app.models import Study

    study = db.get(Study, study_id)
    if study is None:
        return
    study.decompose_status = "running"
    study.decompose_error = None
    db.commit()
    tasks.add_task(run_decompose, study_id)


def run_decompose(study_id: int) -> None:
    """后台拆解:对该 study 全部 ready 资料重跑;先清本资料旧知识点保证幂等。"""
    from app.models import Source, Study, StudySource
    from app.services import knowledge

    with Session(get_engine()) as db:
        study = db.get(Study, study_id)
        if study is None:
            return
        source_ids = db.scalars(
            select(Source.id)
            .join(StudySource, StudySource.source_id == Source.id)
            .where(StudySource.study_id == study_id, Source.parse_status == "ready")
        ).fetchall()
        if not source_ids:
            # 无可拆资料:落 failed,避免状态永远停在 running
            study.decompose_status = "failed"
            study.decompose_error = "没有已解析的资料可拆解"
            db.commit()
            return
        try:
            for source_id in source_ids:
                knowledge.delete_source_kps(db, [study_id], source_id)
                db.flush()
                knowledge.decompose_source(db, study_id, source_id)
                db.commit()
            study = db.get(Study, study_id)
            if study is None:
                return
            study.decompose_status = "done"
            db.commit()
        except Exception as exc:  # noqa: BLE001 失败落状态可再重试(M1-06)
            db.rollback()
            db.expire_all()
            study = db.get(Study, study_id)
            if study is None:
                return
            study.decompose_status = "failed"
            study.decompose_error = str(exc)[:500]
            db.commit()
            print(f"[decompose] study={study_id} 拆解失败: {exc}", file=sys.stderr)


def run_parse(source_id: int) -> None:
    """后台解析入口:独立会话,状态机 pending/processing→ready/failed 落库(M1-06)。"""
    with Session(get_engine()) as db:
        source = db.get(Source, source_id)
        if source is None:
            return
        source.parse_status = "processing"
        source.parse_error = None
        db.commit()
        try:
            if source.raw_path is not None:
                parsed = parsers.parse_file(Path(source.raw_path))
                content_md = parsed.content_md
            elif source.content_md:  # 文本粘贴(M1-07):无文件可解析
                content_md = source.content_md
            else:
                return
            _replace_chunks(db, source, content_md)
            source.content_md = content_md
            source.parse_status = "ready"
            db.commit()
        except Exception as err:  # noqa: BLE001 解析失败给明确提示(M1-02)
            db.rollback()
            source = db.get(Source, source_id)
            if source is None:
                return
            source.parse_status = "failed"
            source.parse_error = str(err)[:500]
            db.commit()
            return

        # 导入完成即拆解(M2-01):每个关联 study 各拆一份;失败落 study 状态可重试(M1-06)
        from app.models import Study
        from app.services import knowledge

        study_ids = db.scalars(
            select(StudySource.study_id).where(StudySource.source_id == source.id)
        ).fetchall()
        for study_id in study_ids:
            study = db.get(Study, study_id)
            if study is None:
                continue
            study.decompose_status = "running"
            study.decompose_error = None
            db.commit()
            try:
                knowledge.decompose_source(db, study_id, source.id)
                study.decompose_status = "done"
                db.commit()
            except Exception as exc:  # noqa: BLE001 失败必须可见,不许静默(M2-01)
                db.rollback()
                db.expire_all()
                study = db.get(Study, study_id)
                if study is None:
                    continue
                study.decompose_status = "failed"
                study.decompose_error = str(exc)[:500]
                db.commit()
                print(f"[decompose] study={study_id} 拆解失败: {exc}", file=sys.stderr)


def _replace_chunks(db: Session, source: Source, content_md: str) -> None:
    from app.services import knowledge

    # 先清旧知识点再删切片:切片删除会级联清引用,之后无法凭引用识别旧知识点
    knowledge.delete_source_kps(
        db,
        study_ids=db.scalars(
            select(StudySource.study_id).where(StudySource.source_id == source.id)
        ).fetchall(),
        source_id=source.id,
    )

    conn = db.connection()
    vecstore.clear_source(conn, source.id)
    db.execute(delete(SourceChunk).where(SourceChunk.source_id == source.id))
    db.flush()
    # 旧切片已删、新切片未插:清掉无主向量,自愈脏状态(否则新切片复用 id 撞 vec 主键)
    vecstore.clear_orphans(conn)

    rows = [
        SourceChunk(
            source_id=source.id,
            seq=seq,
            content=piece.content,
            heading_path=piece.heading_path,
            location=json.dumps(
                {"start_line": piece.start_line, "end_line": piece.end_line},
                ensure_ascii=False,
            ),
        )
        for seq, piece in enumerate(chunker.chunk_markdown(content_md))
    ]
    db.add_all(rows)
    db.flush()

    vectors = embedder.embed_texts([r.content for r in rows])
    vecstore.index_chunks(conn, [(r.id, v) for r, v in zip(rows, vectors, strict=True)])


def list_study_sources(db: Session, study_id: int) -> list[Source]:
    stmt = (
        select(Source)
        .join(StudySource, StudySource.source_id == Source.id)
        .where(StudySource.study_id == study_id)
        .order_by(Source.created_at.desc())
    )
    return list(db.scalars(stmt))


def get_source(db: Session, source_id: int) -> Source | None:
    return db.get(Source, source_id)


def get_source_detail(db: Session, source: Source) -> SourceDetail:
    chunks = db.scalars(
        select(SourceChunk)
        .where(SourceChunk.source_id == source.id)
        .order_by(SourceChunk.seq)
    )
    return SourceDetail(
        id=source.id,
        title=source.title,
        type=source.type,  # type: ignore[arg-type]
        origin=source.origin,
        parse_status=source.parse_status,  # type: ignore[arg-type]
        parse_error=source.parse_error,
        chunks=[ChunkOut(id=c.id, seq=c.seq, content=c.content, heading_path=c.heading_path)
                for c in chunks],
        created_at=source.created_at,
    )


def reparse_source(db: Session, tasks: BackgroundTasks, source: Source) -> Source:
    """重新解析:重启丢任务/失败后的兜底入口(技术总纲 2.4)。"""
    source.parse_status = "pending"
    db.commit()
    db.refresh(source)
    schedule_parse(tasks, source.id)
    return source
