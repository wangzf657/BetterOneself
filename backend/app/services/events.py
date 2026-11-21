"""outline_events 写入助手（数据模型 §3.7）。"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import OutlineEvent


def record_event(
    db: Session,
    study_id: int,
    event_type: str,
    actor: str,
    *,
    kp_id: int | None = None,
    detail: dict[str, Any] | None = None,
    kp_name: str | None = None,
) -> OutlineEvent:
    """kp_name 为名称快照（kp 后续被 merge 删除时事件仍可读，P1-07）。"""
    payload = dict(detail or {})
    if kp_name is not None:
        payload.setdefault("kp_name", kp_name)
    event = OutlineEvent(
        study_id=study_id,
        event_type=event_type,
        actor=actor,
        kp_id=kp_id,
        detail_json=json.dumps(payload, ensure_ascii=False),
    )
    db.add(event)
    return event
