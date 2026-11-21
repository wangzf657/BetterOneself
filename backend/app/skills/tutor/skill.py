"""tutor skill：开场讲解、自由问答、按学习方法调整风格（技术方案 §6、§7.2）。

不改节点状态、不出题；引用只指向传入的编号 sources。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.llm import Scene, stream

PROMPT_PATH = Path(__file__).parent / "prompt.md"

SCHEME_LABELS = {"guided": "带我学", "lecture": "讲给我听", "drill": "帮我过关"}


def _messages(
    task: str, payload: dict[str, object], history: list[dict[str, str]] | None
) -> list[dict[str, str]]:
    system = f"[TASK:{task}]\n" + PROMPT_PATH.read_text(encoding="utf-8")
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    if history:
        messages.extend(history)
    messages.append(
        {
            "role": "user",
            "content": "当前请求上下文（JSON）：\n\n```json\n"
            + json.dumps(payload, ensure_ascii=False, default=str)
            + "\n```",
        }
    )
    return messages


async def opening(
    db: Session, payload: dict[str, object]
) -> AsyncIterator[str]:
    """流式生成首条讲解；payload 见 prompt.md 输入说明。"""
    scene: Scene = "tutor"
    return stream(db, _messages("tutor_opening", payload, None), scene=scene, temperature=0.4)


async def chat_reply(
    db: Session,
    payload: dict[str, object],
    history: list[dict[str, str]],
) -> AsyncIterator[str]:
    """流式回答自由提问；history 为本会话既有消息（role/content）。"""
    scene: Scene = "tutor"
    return stream(db, _messages("tutor_chat", payload, history), scene=scene, temperature=0.5)
