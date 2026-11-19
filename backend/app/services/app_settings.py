"""全局设置(M7-01~04):BYO-Key 加密落库;运行时配置读库优先、.env 兜底。"""

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import Setting
from app.services import secretbox

DEFAULTS = {
    "llm_base_url": "",
    "llm_model": "",
    "embed_base_url": "",
    "embed_model": "",
    "daily_review_limit": 20,
    "inactivity_threshold_days": 5,
}


def get_row(db: Session) -> Setting:
    row = db.get(Setting, 1)
    if row is None:
        row = Setting(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def peek_row(db: Session) -> Setting | None:
    """只读取行:resolve 路径可能在外层写事务中被调用(SQLite 单写者),绝不写库。"""
    return db.get(Setting, 1)


def out_shape(db: Session, row: Setting) -> dict[str, Any]:
    """输出形态:key 只回传是否已设置,永不回传明文(M7-01)。"""
    return {
        "llm_base_url": row.llm_base_url or None,
        "llm_model": row.llm_model or None,
        "llm_key_set": bool(row.llm_api_key_enc),
        "embed_base_url": row.embed_base_url or None,
        "embed_model": row.embed_model or None,
        "embed_key_set": bool(row.embed_api_key_enc),
        "daily_review_limit": row.daily_review_limit,
        "inactivity_threshold_days": row.inactivity_threshold_days,
        "fsrs_params": json.loads(row.fsrs_params_json) if row.fsrs_params_json else None,
    }


def update(db: Session, data: dict[str, Any]) -> Setting:
    row = get_row(db)
    for field in ("llm_base_url", "llm_model", "embed_base_url", "embed_model"):
        if field in data and data[field] is not None:
            setattr(row, field, str(data[field]))
    if data.get("llm_api_key"):
        row.llm_api_key_enc = secretbox.encrypt(str(data["llm_api_key"]))
    if data.get("embed_api_key"):
        row.embed_api_key_enc = secretbox.encrypt(str(data["embed_api_key"]))
    for field in ("daily_review_limit", "inactivity_threshold_days"):
        if field in data and data[field] is not None:
            setattr(row, field, int(data[field]))
    db.commit()
    db.refresh(row)
    return row


def resolve_llm(db: Session) -> dict[str, str]:
    """库内设置优先,.env 兜底(技术总纲 2.6 开发期直读 env)。"""
    from app.config import get_config

    cfg = get_config()
    row = peek_row(db)
    if row is None:
        return {"base_url": cfg.llm_base_url, "api_key": cfg.llm_api_key, "model": cfg.llm_model}
    key = secretbox.decrypt(row.llm_api_key_enc) if row.llm_api_key_enc else cfg.llm_api_key
    return {
        "base_url": row.llm_base_url or cfg.llm_base_url,
        "api_key": key,
        "model": row.llm_model or cfg.llm_model,
    }


def resolve_embed(db: Session) -> dict[str, str]:
    from app.config import get_config

    cfg = get_config()
    row = peek_row(db)
    if row is None:
        return {
            "base_url": cfg.embed_base_url,
            "api_key": cfg.embed_api_key,
            "model": cfg.embed_model,
        }
    key = secretbox.decrypt(row.embed_api_key_enc) if row.embed_api_key_enc else cfg.embed_api_key
    return {
        "base_url": row.embed_base_url or cfg.embed_base_url,
        "api_key": key,
        "model": row.embed_model or cfg.embed_model,
    }
