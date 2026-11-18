"""资料管理与解析流水线(M1-02/05/06):上传→后台解析→切片→向量化→ready。"""

import json
import time
from pathlib import Path

from fastapi import BackgroundTasks
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_config
from app.db import get_engine
from app.ingest import chunker, embedder, parsers, vecstore
from app.models import Source, SourceChunk, StudySource
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


def schedule_parse(tasks: BackgroundTasks, source_id: int) -> None:
    tasks.add_task(run_parse, source_id)


def run_parse(source_id: int) -> None:
    """后台解析入口:独立会话,状态机 pending/processing→ready/failed 落库(M1-06)。"""
    with Session(get_engine()) as db:
        source = db.get(Source, source_id)
        if source is None or source.raw_path is None:
            return
        source.parse_status = "processing"
        source.parse_error = None
        db.commit()
        try:
            parsed = parsers.parse_file(Path(source.raw_path))
            _replace_chunks(db, source, parsed.content_md)
            source.content_md = parsed.content_md
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

        # 导入完成即拆解(M2-01):每个关联 study 各拆一份;拆解失败不影响解析结果
        from app.services import knowledge

        study_ids = db.scalars(
            select(StudySource.study_id).where(StudySource.source_id == source.id)
        ).fetchall()
        for study_id in study_ids:
            try:
                knowledge.decompose_source(db, study_id, source.id)
                db.commit()
            except Exception:  # noqa: BLE001
                db.rollback()


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
