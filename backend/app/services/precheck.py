"""解析后统一预检（V0.1.1 技术设计 §3，B6-02）：embedding 必检、LLM 勾选才检。

每路一次最小真实请求；维度必须等于 vec_chunks 的建表维度——换 embedding 模型后维度不符
会写脏向量表（V0.1 真机教训）。探测只报告结果，落状态与启动任务由调用方（pipeline）负责。
"""

from __future__ import annotations

import os
from collections.abc import Awaitable
from dataclasses import dataclass

from openai import APIConnectionError, APIError, APIStatusError, APITimeoutError
from sqlalchemy.orm import Session

from app.core.config import get_config
from app.core.db import EMBED_DIM
from app.core.errors import LLMNotConfigured
from app.core.llm import _make_probe_client, load_embed_config, load_llm_config, record_usage

NOT_CONFIGURED = "not_configured"
REQUEST_FAILED = "request_failed"
DIM_MISMATCH = "dim_mismatch"


@dataclass(frozen=True)
class LaneResult:
    ok: bool
    reason: str | None = None  # not_configured / request_failed / dim_mismatch
    detail: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {"ok": self.ok, "reason": self.reason, "detail": self.detail}


class ProbeFailed(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def _stub_fail(lane: str) -> LaneResult | None:
    """E2E 专用：BO_STUB_PRECHECK_FAIL=embedding,llm 让指定路模拟不通。"""
    if lane in os.environ.get("BO_STUB_PRECHECK_FAIL", "").split(","):
        return LaneResult(False, REQUEST_FAILED, f"{lane} 服务连接失败（桩：模拟不通）")
    return None


async def _guarded[T](label: str, call: Awaitable[T]) -> T:
    """异常信息只取类名与 HTTP 状态码：响应体可能回显请求内容，不能进日志与界面。"""
    try:
        return await call
    except APIStatusError as e:
        raise ProbeFailed(f"{label}返回错误（HTTP {e.status_code}）") from e
    except (APIConnectionError, APITimeoutError) as e:
        raise ProbeFailed(f"{label}连接失败（{type(e).__name__}）") from e
    except APIError as e:
        raise ProbeFailed(f"{label}返回错误（{e.__class__.__name__}）") from e


async def probe_embedding(db: Session) -> LaneResult:
    if get_config().llm_stub:
        return _stub_fail("embedding") or LaneResult(ok=True)
    try:
        cfg = load_embed_config(db)
        client = _make_probe_client(cfg)
        resp = await _guarded("embedding 服务", client.embeddings.create(model=cfg.model, input=["预检"]))
    except LLMNotConfigured:
        return LaneResult(False, NOT_CONFIGURED, "未配置 embedding 服务，请到设置页补全")
    except ProbeFailed as e:
        return LaneResult(False, REQUEST_FAILED, e.detail)

    record_usage(db, "embed", resp.usage.prompt_tokens, 0)
    dim = len(resp.data[0].embedding)
    if dim != EMBED_DIM:
        return LaneResult(
            False,
            DIM_MISMATCH,
            f"embedding 维度不符：期望 {EMBED_DIM}，实际 {dim}（请检查 embed 模型配置）",
        )
    return LaneResult(ok=True)


async def probe_llm(db: Session) -> LaneResult:
    if get_config().llm_stub:
        return _stub_fail("llm") or LaneResult(ok=True)
    try:
        cfg = load_llm_config(db)
        client = _make_probe_client(cfg)
        resp = await _guarded(
            "AI 服务",
            client.chat.completions.create(
                model=cfg.model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
            ),
        )
    except LLMNotConfigured:
        return LaneResult(False, NOT_CONFIGURED, "未配置 AI 服务，请到设置页补全")
    except ProbeFailed as e:
        return LaneResult(False, REQUEST_FAILED, e.detail)

    record_usage(db, "outline", resp.usage.prompt_tokens if resp.usage else 1, 0)
    return LaneResult(ok=True)
