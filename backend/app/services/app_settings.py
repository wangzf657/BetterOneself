"""设置与用量服务（B5-02/04、P1-06）：密钥三语义、掩码、用量查询。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import encrypt_secret, mask_secret, try_decrypt
from app.core.errors import Validation
from app.models import Setting, Source, UsageDay

LLM_KEYS = ("llm.base_url", "llm.model", "llm.api_key")
EMBED_KEYS = ("embed.base_url", "embed.model", "embed.api_key")


def _mask_or_none(db: Session, key: str) -> str | None:
    row = db.get(Setting, key)
    plain = try_decrypt(row.value) if row and key.endswith("api_key") else (row.value if row else None)
    if plain is None:
        return None
    return mask_secret(plain) if key.endswith("api_key") else plain


def get_settings(db: Session) -> dict[str, Any]:
    statuses = [s.embed_status for s in db.query(Source).all()]
    worst = None
    if "failed" in statuses:
        worst = "failed"
    elif "degraded" in statuses:
        worst = "degraded"
    elif "precheck_failed" in statuses:
        worst = "precheck_failed"
    elif statuses and all(s == "ready" for s in statuses):
        worst = "ready"
    elif "running" in statuses:
        worst = "running"
    elif statuses:
        worst = "pending"
    embed_errors = [s.embed_error for s in db.query(Source).all() if s.embed_error]
    return {
        "llm": {
            "base_url": _mask_or_none(db, "llm.base_url"),
            "model": _mask_or_none(db, "llm.model"),
            "api_key": _mask_or_none(db, "llm.api_key"),
        },
        "embed": {
            "base_url": _mask_or_none(db, "embed.base_url"),
            "model": _mask_or_none(db, "embed.model"),
            "api_key": _mask_or_none(db, "embed.api_key"),
            "status": worst,
            "error": embed_errors[0] if embed_errors else None,
            "note": (
                "资料处理服务未配置或失败时，仅失去跨节点细节检索补足；"
                "当前节点的讲解、测验与原文不受影响。"
            ),
        },
    }


def put_settings(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """PUT 语义（P1-06）：字段缺省保持不变、置 null 清除、填新值替换；
    掩码提交按未修改处理；某项失败不清空其他项。"""
    errors: list[str] = []
    for group, keys in (("llm", LLM_KEYS), ("embed", EMBED_KEYS)):
        body = payload.get(group)
        if not isinstance(body, dict):
            continue
        for key in keys:
            short = key.split(".", 1)[1]  # 请求体用短名（base_url/model/api_key）
            if short not in body:
                continue  # 缺省 → 不变
            value = body[short]
            if key.endswith("api_key"):
                current = db.get(Setting, key)
                current_plain = try_decrypt(current.value) if current else None
                if value is None:
                    new_value = None  # 置空即清除
                elif not isinstance(value, str) or not value.strip():
                    errors.append(f"{key} 不能为空字符串（清除请置 null）")
                    continue
                elif current_plain and value == mask_secret(current_plain):
                    continue  # 掩码不是合法输入：按未修改处理
                else:
                    new_value = encrypt_secret(value.strip())
            else:
                if value is None:
                    new_value = None
                elif isinstance(value, str):
                    if key.endswith("base_url") and value and not value.startswith(("http://", "https://")):
                        errors.append(f"{key} 必须是 http(s):// 开头的地址")
                        continue
                    new_value = value.strip() or None
                else:
                    errors.append(f"{key} 必须是字符串")
                    continue
            row = db.get(Setting, key)
            if row is None:
                db.add(Setting(key=key, value=new_value))
            else:
                row.value = new_value
    if errors:
        db.rollback()
        raise Validation("；".join(errors))
    db.commit()
    return get_settings(db)


def usage_between(db: Session, date_from: str | None, date_to: str | None) -> list[dict[str, Any]]:
    q = select(UsageDay)
    if date_from:
        q = q.where(UsageDay.date >= date_from)
    if date_to:
        q = q.where(UsageDay.date <= date_to)
    rows = db.execute(q.order_by(UsageDay.date.desc(), UsageDay.scene)).scalars().all()
    return [
        {
            "date": r.date,
            "scene": r.scene,
            "requests": r.requests,
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
        }
        for r in rows
    ]
