"""设置与用量(M7-01/04)。key 加密落库,任何输出不含明文(M7-01 验收)。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import app_settings
from app.services import usage as usage_svc

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)) -> dict:
    return app_settings.out_shape(db, app_settings.get_row(db))


class SettingsUpdate(BaseModel):
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    embed_base_url: str | None = None
    embed_api_key: str | None = None
    embed_model: str | None = None
    daily_review_limit: int | None = None
    inactivity_threshold_days: int | None = None


@router.put("/settings")
def update_settings(data: SettingsUpdate, db: Session = Depends(get_db)) -> dict:
    row = app_settings.update(db, data.model_dump(exclude_none=True))
    return app_settings.out_shape(db, row)


@router.get("/usage")
def get_usage(db: Session = Depends(get_db)) -> list[dict]:
    return usage_svc.summary(db)
