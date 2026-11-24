"""统一 LLM 薄封装（技术方案 §2、§6）：OpenAI 兼容 SDK 直调，无编排框架。

- 配置来自 settings 表（llm.* / embed.*），密钥解密后仅在内存使用；
- 任何日志与异常信息不包含明文 key（B5-02）；
- 每次调用按场景与日期写 usage_days，写入失败记录错误、不静默（注意事项 #9）；
- BO_LLM_STUB=1 时使用确定性桩（E2E/开发），不触网。
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

from openai import APIConnectionError, APIError, APITimeoutError, AsyncOpenAI
from sqlalchemy.orm import Session

from app.core import stub_llm
from app.core.config import get_config
from app.core.errors import LLMError, LLMNotConfigured, LLMUnavailable
from app.models import Setting, UsageDay

logger = logging.getLogger(__name__)

Scene = Literal["outline", "tutor", "quiz", "embed"]

_LLM_KEYS = ("llm.base_url", "llm.model", "llm.api_key")
_EMBED_KEYS = ("embed.base_url", "embed.model", "embed.api_key")


@dataclass
class ServiceConfig:
    base_url: str
    model: str
    api_key: str


def _load_service_config(db: Session, keys: tuple[str, ...], prefix: str) -> ServiceConfig:
    from app.core.crypto import try_decrypt

    rows = {r.key: r.value for r in db.query(Setting).filter(Setting.key.in_(keys)).all()}
    base_url = (rows.get(f"{prefix}.base_url") or "").strip()
    model = (rows.get(f"{prefix}.model") or "").strip()
    api_key = try_decrypt(rows.get(f"{prefix}.api_key"))
    if not base_url or not model or not api_key:
        missing = [k.split(".", 1)[1] for k in keys if not rows.get(k)]
        raise LLMNotConfigured(f"AI 服务配置不完整（缺 {'、'.join(missing)}），请到设置页补全")
    return ServiceConfig(base_url=base_url, model=model, api_key=api_key)


def load_llm_config(db: Session) -> ServiceConfig:
    return _load_service_config(db, _LLM_KEYS, "llm")


def load_embed_config(db: Session) -> ServiceConfig:
    return _load_service_config(db, _EMBED_KEYS, "embed")


def llm_configured(db: Session) -> bool:
    try:
        load_llm_config(db)
        return True
    except LLMError:
        return False


def record_usage(db: Session, scene: Scene, prompt_tokens: int, completion_tokens: int) -> None:
    """独立短事务写用量；失败记录错误，不静默吞掉（注意事项 #9）。"""
    from app.core.db import get_session_local
    from app.models import utcnow

    date = utcnow().strftime("%Y-%m-%d")
    try:
        with get_session_local()() as s:
            row = (
                s.query(UsageDay)
                .filter(UsageDay.date == date, UsageDay.scene == scene)
                .one_or_none()
            )
            if row is None:
                s.add(
                    UsageDay(
                        date=date,
                        scene=scene,
                        requests=1,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                    )
                )
            else:
                row.requests += 1
                row.prompt_tokens += prompt_tokens
                row.completion_tokens += completion_tokens
            s.commit()
    except Exception:
        logger.exception("用量写入失败 scene=%s date=%s（不静默：已记录错误）", scene, date)


def _make_client(cfg: ServiceConfig) -> AsyncOpenAI:
    return AsyncOpenAI(base_url=cfg.base_url, api_key=cfg.api_key, timeout=180.0, max_retries=1)


def _make_probe_client(cfg: ServiceConfig) -> AsyncOpenAI:
    # 预检专用：服务不通时不能把一次探测挂到正式调用的 180 秒
    return AsyncOpenAI(base_url=cfg.base_url, api_key=cfg.api_key, timeout=15.0, max_retries=0)


async def complete(
    db: Session,
    messages: list[dict[str, str]],
    *,
    scene: Scene,
    temperature: float = 0.2,
    max_tokens: int | None = None,
) -> str:
    """非流式补全（outline_planner / quiz / 简答评语）。"""
    if get_config().llm_stub:
        result = stub_llm.complete(messages, scene=scene)
        record_usage(db, scene, 0, 0)  # 桩同样入账，用量口径在开发模式也完整（BUG-002）
        return result

    cfg = load_llm_config(db)
    try:
        resp = await _make_client(cfg).chat.completions.create(
            model=cfg.model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except LLMError:
        raise
    except (APIConnectionError, APITimeoutError) as e:
        raise LLMUnavailable(f"模型服务连接失败：{type(e).__name__}") from e
    except APIError as e:
        raise LLMUnavailable(f"模型服务返回错误：{e.__class__.__name__}") from e

    content = resp.choices[0].message.content or ""
    usage = resp.usage
    record_usage(
        db,
        scene,
        usage.prompt_tokens if usage else 0,
        usage.completion_tokens if usage else 0,
    )
    return content


async def stream(
    db: Session,
    messages: list[dict[str, str]],
    *,
    scene: Scene,
    temperature: float = 0.6,
    max_tokens: int | None = None,
) -> AsyncIterator[str]:
    """流式补全（tutor 讲解与问答）。完成后记录一次用量。"""
    if get_config().llm_stub:
        async for delta in stub_llm.stream(messages, scene=scene):
            yield delta
        record_usage(db, scene, 0, 0)
        return

    cfg = load_llm_config(db)
    try:
        from openai import AsyncStream

        created = await _make_client(cfg).chat.completions.create(
            model=cfg.model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        assert isinstance(created, AsyncStream)
        stream_iter = created
        async for event in stream_iter:
            if event.choices and event.choices[0].delta.content:
                yield event.choices[0].delta.content
    except LLMError:
        raise
    except (APIConnectionError, APITimeoutError) as e:
        raise LLMUnavailable(f"模型服务连接失败：{type(e).__name__}") from e
    except APIError as e:
        raise LLMUnavailable(f"模型服务返回错误：{e.__class__.__name__}") from e
    # shortcut: 流式不要求 provider 返回 usage, 记一次请求; 需要精确 token 时升级 include_usage
    record_usage(db, scene, 0, 0)


async def embed_texts(db: Session, texts: list[str]) -> list[list[float]]:
    """embedding 独立配置（硅基流动 bge-m3，1024 维 float32）。"""
    from app.core.db import EMBED_DIM

    if get_config().llm_stub:
        vectors = stub_llm.embed_texts(texts, dim=EMBED_DIM)
        record_usage(db, "embed", sum(len(t) for t in texts) // 2, 0)
        return vectors

    cfg = load_embed_config(db)
    try:
        resp = await _make_client(cfg).embeddings.create(model=cfg.model, input=texts)
    except APIError as e:
        raise LLMUnavailable(f"embedding 服务返回错误：{e.__class__.__name__}") from e
    except (APIConnectionError, APITimeoutError) as e:
        raise LLMUnavailable(f"embedding 服务连接失败：{type(e).__name__}") from e
    vectors = [d.embedding for d in resp.data]
    for v in vectors:
        if len(v) != EMBED_DIM:
            raise LLMUnavailable(
                f"embedding 维度不符：期望 {EMBED_DIM}，实际 {len(v)}（请检查 embed 模型配置）"
            )
    record_usage(db, "embed", sum(len(t) for t in texts) // 2, 0)
    return vectors


def extract_json(text: str) -> Any:
    """从模型输出中提取 JSON（容忍代码围栏与前后缀文字）。失败抛 LLMError。"""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        first_nl = cleaned.find("\n")
        cleaned = cleaned[first_nl + 1 : cleaned.rfind("```")] if first_nl != -1 else cleaned
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise LLMUnavailable("模型未返回合法 JSON")
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as e:
        raise LLMUnavailable(f"模型返回的 JSON 无法解析：{e}") from e
