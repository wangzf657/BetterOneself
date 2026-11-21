"""设置与用量 API（B5、接口设计 §6）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas import SettingsPayload, SettingsPut, UsageRow
from app.services import app_settings

router = APIRouter(tags=["settings"])


@router.get("/settings", response_model=SettingsPayload)
def get_settings(db: Session = Depends(get_db)) -> dict[str, object]:
    return app_settings.get_settings(db)


@router.put("/settings", response_model=SettingsPayload)
def put_settings(body: SettingsPut, db: Session = Depends(get_db)) -> dict[str, object]:
    # exclude_unset：请求中未出现的字段保持 absent，"缺省 → 不变"语义才能在 HTTP 层成立
    # （显式 null 仍保留 → 清除；见接口设计 P1-06 三语义）
    return app_settings.put_settings(db, body.model_dump(exclude_none=False, exclude_unset=True))


@router.get("/usage", response_model=list[UsageRow])
def usage(
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    return app_settings.usage_between(db, date_from, date_to)
