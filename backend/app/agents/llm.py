"""LLM 统一薄入口(技术总纲 2.3 的"单次调用"类):client 构造、stub、结构化输出。

配置经 app_settings 解析(库内 BYO-Key 优先,.env 兜底);每次成功调用记录 usage(M7-04)。
"""

import re
from collections.abc import Iterator
from contextlib import contextmanager

from openai import OpenAI
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session as OrmSession

from app.agents import stubs

# glm-5.3-flash 为思考型模型,短问答也产生 reasoning tokens(技术总纲 1)
_MAX_TOKENS = 4096


@contextmanager
def _session():
    from app.db import get_engine

    with OrmSession(get_engine()) as s:
        yield s


def _client_config() -> tuple[bool, OpenAI | None, str]:
    """(是否 stub, client, model)。配置库内优先,.env 兜底。"""
    from app.config import get_config
    from app.services import app_settings

    with _session() as db:
        resolved = app_settings.resolve_llm(db)
    cfg = get_config()
    stub = cfg.stub_llm or not resolved["api_key"]
    client = (
        None
        if stub
        else OpenAI(base_url=resolved["base_url"], api_key=resolved["api_key"])
    )
    return stub, client, resolved["model"]


def chat(messages: list[dict], *, temperature: float = 0.3, scene: str = "chat") -> str:
    stub, client, model = _client_config()
    if stub:
        return stubs.stub_chat(messages)
    assert client is not None
    resp = client.chat.completions.create(
        model=model,
        messages=messages,  # type: ignore[arg-type]  # 动态构造的消息字面量
        temperature=temperature,
        max_tokens=_MAX_TOKENS,
    )
    _record_usage(scene, resp)
    return resp.choices[0].message.content or ""


def chat_stream(
    messages: list[dict], *, temperature: float = 0.3, scene: str = "chat"
) -> Iterator[str]:
    stub, client, model = _client_config()
    if stub:
        # stub 也按块吐出,保证前端流式路径与真实一致
        text = stubs.stub_chat(messages)
        for i in range(0, len(text), 24):
            yield text[i : i + 24]
        return
    assert client is not None
    stream = client.chat.completions.create(
        model=model,
        messages=messages,  # type: ignore[arg-type]  # 动态构造的消息字面量
        temperature=temperature,
        max_tokens=_MAX_TOKENS,
        stream=True,
    )
    usage_taken = False
    for delta in stream:
        chunk = delta.choices[0].delta.content  # type: ignore[union-attr]  # SDK 流式重载类型过宽
        if chunk:
            yield chunk
        chunk_usage = getattr(delta, "usage", None) if not isinstance(delta, tuple) else None
        if not usage_taken and chunk_usage is not None:
            _record_usage(scene, chunk_usage)
            usage_taken = True


def _record_usage(scene: str, resp) -> None:
    usage = getattr(resp, "usage", None)
    if usage is None:
        return
    from app.services import usage

    usage.record(scene, usage.prompt_tokens or 0, usage.completion_tokens or 0)


def parse_json[T: BaseModel](
    messages: list[dict], schema: type[T], *, temperature: float = 0.1, scene: str = "chat"
) -> T:
    """结构化输出:JSON 约束 + pydantic 校验 + 一次纠错重试。"""
    attempt = [
        *messages,
        {"role": "system", "content": "只输出符合 schema 的 JSON 对象,不要 markdown 代码块。"},
    ]
    for _ in range(2):
        raw = chat(attempt, temperature=temperature, scene=scene)
        try:
            return schema.model_validate_json(_strip_fences(raw))
        except ValidationError as err:
            attempt += [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": f"JSON 不符合要求:{err}\n重新只输出 JSON。"},
            ]
    raise ValueError("LLM 结构化输出两次未通过校验")


def _strip_fences(text: str) -> str:
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    return m.group(1).strip() if m else text.strip()
