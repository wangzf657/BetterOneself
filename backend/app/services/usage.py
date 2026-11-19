"""用量统计(M7-04):按天×场景聚合 token 与请求数;stub 调用不记。"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import UsageDay


def record(scene: str, prompt_tokens: int, completion_tokens: int, requests: int = 1) -> None:
    try:
        with Session(get_engine()) as db:
            day = date.today()
            row = db.scalar(select(UsageDay).where(UsageDay.date == day, UsageDay.scene == scene))
            if row is None:
                row = UsageDay(date=day, scene=scene)
                db.add(row)
            row.prompt_tokens += prompt_tokens
            row.completion_tokens += completion_tokens
            row.requests += requests
            db.commit()
    except Exception:  # noqa: BLE001 统计失败不影响主流程
        pass


def summary(db: Session) -> list[dict]:
    rows = db.scalars(select(UsageDay).order_by(UsageDay.date.desc())).fetchall()
    return [
        {
            "date": str(r.date),
            "scene": r.scene,
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "requests": r.requests,
        }
        for r in rows
    ]
