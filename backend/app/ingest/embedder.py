"""Embedding:硅基流动 bge-m3(OpenAI 兼容,1024 维),分批+重试;stub 模式供测试/E2E。

配置经 app_settings 解析(库内 BYO-Key 优先,.env 兜底)。
"""

import hashlib
import struct
import time

from openai import OpenAI

from app.config import get_config

EMBED_DIM = 1024
_BATCH = 16
_RETRIES = 3


def _resolve() -> tuple[bool, OpenAI | None, str]:
    from sqlalchemy.orm import Session as OrmSession

    from app.db import get_engine
    from app.services import app_settings

    with OrmSession(get_engine()) as db:
        resolved = app_settings.resolve_embed(db)
    stub = get_config().stub_llm or not resolved["api_key"]
    client = (
        None
        if stub
        else OpenAI(base_url=resolved["base_url"], api_key=resolved["api_key"])
    )
    return stub, client, resolved["model"]


def embed_texts(texts: list[str], stub: bool | None = None) -> list[bytes]:
    """返回 sqlite-vec 可直接写入的 float32 序列化 bytes。"""
    cfg_stub, client, model = _resolve()
    if stub is None:
        stub = cfg_stub
    if stub or client is None:
        return [_stub_vector(t) for t in texts]

    vectors: list[bytes] = []
    for start in range(0, len(texts), _BATCH):
        batch = texts[start : start + _BATCH]
        last_err: Exception | None = None
        for attempt in range(_RETRIES):
            try:
                resp = client.embeddings.create(model=model, input=batch)
                vectors.extend(_serialize_float32(v.embedding) for v in resp.data)
                if getattr(resp, "usage", None):
                    from app.services import usage

                    usage.record("embed", resp.usage.prompt_tokens or 0, 0)
                last_err = None
                break
            except Exception as err:  # noqa: BLE001 免费档限流,统一退避重试
                last_err = err
                time.sleep(2**attempt)
        if last_err is not None:
            raise last_err
    return vectors


def _serialize_float32(values: list[float]) -> bytes:
    return struct.pack(f"<{len(values)}f", *values)


def _stub_vector(text: str) -> bytes:
    """确定性伪向量:同文本同向量,机制测试不依赖网络。"""
    state = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")
    values = []
    for _ in range(EMBED_DIM):
        state = (state * 6364136223846793005 + 1442695040888963407) % (1 << 64)
        values.append((state / (1 << 64)) - 0.5)
    norm = sum(v * v for v in values) ** 0.5 or 1.0
    return _serialize_float32([v / norm for v in values])
