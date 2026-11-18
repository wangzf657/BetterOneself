"""Embedding:硅基流动 bge-m3(OpenAI 兼容,1024 维),分批+重试;stub 模式供测试/E2E。"""

import hashlib
import struct
import time

from openai import OpenAI

from app.config import get_config

EMBED_DIM = 1024
_BATCH = 16
_RETRIES = 3


def embed_texts(texts: list[str], stub: bool | None = None) -> list[bytes]:
    """返回 sqlite-vec 可直接写入的 float32 序列化 bytes。"""
    cfg = get_config()
    if stub is None:
        stub = cfg.stub_llm or not cfg.embed_api_key
    if stub:
        return [_stub_vector(t) for t in texts]

    client = OpenAI(base_url=cfg.embed_base_url, api_key=cfg.embed_api_key)
    vectors: list[bytes] = []
    for start in range(0, len(texts), _BATCH):
        batch = texts[start : start + _BATCH]
        last_err: Exception | None = None
        for attempt in range(_RETRIES):
            try:
                resp = client.embeddings.create(model=cfg.embed_model, input=batch)
                vectors.extend(_serialize_float32(v.embedding) for v in resp.data)
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
