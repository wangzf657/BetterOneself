"""quiz skill：按节点出题与简答练习评语（技术方案 §6、§7.3）。

不判正误、不决定点亮与通过线（service 比对与判定）；不做卡片。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.llm import Scene, complete, extract_json

PROMPT_PATH = Path(__file__).parent / "prompt.md"
TASK = "quiz_gen"
COMMENT_TASK = "quiz_comment"


class QuizQuestionDraft(BaseModel):
    no: int
    type: Literal["choice", "judge", "short"]
    graded: bool
    stem: str = Field(min_length=1)
    options: list[str] | None = None
    answer: str | bool | None = None
    explanation: str | None = None
    refs: list[int] = Field(default_factory=list)
    reference_answer: str | None = None
    dimension: str | None = None


class QuizDraft(BaseModel):
    questions: list[QuizQuestionDraft]


async def generate(db: Session, payload: dict[str, object]) -> str:
    """生成一组测验题（题面 + 服务端答案一体产出，答案面由 service 持有）。"""
    messages = [
        {"role": "system", "content": f"[TASK:{TASK}]\n" + PROMPT_PATH.read_text(encoding="utf-8")},
        {
            "role": "user",
            "content": "命题请求上下文（JSON）：\n\n```json\n"
            + json.dumps(payload, ensure_ascii=False, default=str)
            + "\n```",
        },
    ]
    scene: Scene = "quiz"
    return await complete(db, messages, scene=scene, temperature=0.3)


def parse_quiz(raw: str) -> QuizDraft:
    return QuizDraft.model_validate(extract_json(raw))


async def comment_short_answer(
    db: Session,
    *,
    stem: str,
    reference_answer: str | None,
    user_answer: str,
    sources_text: str,
) -> str:
    """简答练习评语：具体、可操作，不计入成绩（B4-01）。"""
    messages = [
        {
            "role": "system",
            "content": (
                f"[TASK:{COMMENT_TASK}]\n你是阅卷助教，为一道**不计分**的简答练习写评语。"
                "评语要具体：指出用户答对了什么、缺了什么、建议从哪些角度补全（80–150 字），"
                "并可建议回看原文（可用 [n] 引用编号）。不判分、不指责。"
            ),
        },
        {
            "role": "user",
            "content": "```json\n"
            + json.dumps(
                {
                    "stem": stem,
                    "reference_answer": reference_answer,
                    "user_answer": user_answer,
                    "sources": sources_text[:6000],
                },
                ensure_ascii=False,
            )
            + "\n```",
        },
    ]
    scene: Scene = "quiz"
    return (await complete(db, messages, scene=scene, temperature=0.2)).strip()
