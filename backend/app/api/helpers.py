"""api 层公共小工具:chunk→source 映射(引用回跳)。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SourceChunk


def source_of_chunks(db: Session, chunk_ids: list[int | None]) -> dict[int, int]:
    ids = [c for c in chunk_ids if c is not None]
    if not ids:
        return {}
    rows = db.execute(
        select(SourceChunk.id, SourceChunk.source_id).where(SourceChunk.id.in_(ids))
    ).all()
    return dict(rows)
