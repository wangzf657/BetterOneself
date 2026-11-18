"""LLM 统一薄入口(技术总纲 2.3 的"单次调用"类):client 构造、stub、结构化输出。"""

import re
from collections.abc import Iterator

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from app.agents import stubs
from app.config import get_config

# glm-5.3-flash 为思考型模型,短问答也产生 reasoning tokens(技术总纲 1)
_MAX_TOKENS = 4096


def _client_config() -> tuple[bool, OpenAI | None]:
    cfg = get_config()
    if cfg.stub_llm or not cfg.llm_api_key:
        return True, None
    return False, OpenAI(base_url=cfg.llm_base_url, api_key=cfg.llm_api_key)


def chat(messages: list[dict], *, temperature: float = 0.3) -> str:
    stub, client = _client_config()
    if stub:
        return stubs.stub_chat(messages)
    assert client is not None
    resp = client.chat.completions.create(
        model=get_config().llm_model,
        messages=messages,  # type: ignore[arg-type]  # 动态构造的消息字面量
        temperature=temperature,
        max_tokens=_MAX_TOKENS,
    )
    return resp.choices[0].message.content or ""


def chat_stream(messages: list[dict], *, temperature: float = 0.3) -> Iterator[str]:
    stub, client = _client_config()
    if stub:
        # stub 也按块吐出,保证前端流式路径与真实一致
        text = stubs.stub_chat(messages)
        for i in range(0, len(text), 24):
            yield text[i : i + 24]
        return
    assert client is not None
    stream = client.chat.completions.create(
        model=get_config().llm_model,
        messages=messages,  # type: ignore[arg-type]  # 动态构造的消息字面量
        temperature=temperature,
        max_tokens=_MAX_TOKENS,
        stream=True,
    )
    for delta in stream:
        piece = delta.choices[0].delta.content  # type: ignore[union-attr]  # SDK 流式重载类型过宽
        if piece:
            yield piece


def parse_json[T: BaseModel](
    messages: list[dict], schema: type[T], *, temperature: float = 0.1
) -> T:
    """结构化输出:JSON 约束 + pydantic 校验 + 一次纠错重试。"""
    attempt = [
        *messages,
        {"role": "system", "content": "只输出符合 schema 的 JSON 对象,不要 markdown 代码块。"},
    ]
    for _ in range(2):
        raw = chat(attempt, temperature=temperature)
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
