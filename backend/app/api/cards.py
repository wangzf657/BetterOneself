"""复习与卡片路由(M3-05, M4-01/02/03)。"""

from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.helpers import source_of_chunks
from app.db import get_db
from app.models import Card
from app.schemas.card import CardCreate, CardOut, RateIn
from app.services import review, studies

router = APIRouter(prefix="/api", tags=["review"])


def _with_source(rows: Sequence[Card], db: Session) -> list[CardOut]:
    smap = source_of_chunks(db, [r.chunk_id for r in rows])
    out = []
    for r in rows:
        item = CardOut.model_validate(r)
        item.source_id = smap.get(r.chunk_id) if r.chunk_id else None
        out.append(item)
    return out


@router.get("/review/queue", response_model=list[CardOut])
def queue(study_id: int | None = None, db: Session = Depends(get_db)) -> list[CardOut]:
    return _with_source(review.get_queue(db, study_id), db)


@router.get("/review/params")
def params(db: Session = Depends(get_db)) -> dict:
    return review.fsrs_params(db)


@router.get("/studies/{study_id}/cards", response_model=list[CardOut])
def list_cards(study_id: int, db: Session = Depends(get_db)) -> list[CardOut]:
    rows = db.scalars(
        select(Card).where(Card.study_id == study_id).order_by(Card.due)
    ).fetchall()
    return _with_source(rows, db)


@router.post("/studies/{study_id}/cards", response_model=CardOut, status_code=201)
def create_card(study_id: int, data: CardCreate, db: Session = Depends(get_db)) -> CardOut:
    if studies.get_study(db, study_id) is None:
        raise HTTPException(status_code=404, detail="study not found")
    card = review.create_card(
        db,
        study_id=study_id,
        kp_id=data.kp_id,
        front=data.front,
        back_md=data.back_md,
        chunk_id=data.chunk_id,
        origin=data.origin,
    )
    item = CardOut.model_validate(card)
    item.source_id = smap_single(db, card.chunk_id)
    return item


def smap_single(db: Session, chunk_id: int | None) -> int | None:
    if chunk_id is None:
        return None
    return source_of_chunks(db, [chunk_id]).get(chunk_id)


@router.post("/cards/{card_id}/rate", response_model=CardOut)
def rate(card_id: int, data: RateIn, db: Session = Depends(get_db)) -> CardOut:
    card = db.get(Card, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="card not found")
    rated = review.rate_card(db, card, data.rating)
    item = CardOut.model_validate(rated)
    item.source_id = smap_single(db, rated.chunk_id)
    return item
