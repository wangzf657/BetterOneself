"""outline_planner skill：章节摘要消费、全书总述、五类结构操作（技术方案 §5、§6）。

不输入正文逐字内容（ref manifest 仅元数据）；不建依赖图；
结构化输出校验失败即本次规划失败，保留原树（由 service 负责）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.llm import Scene, complete, extract_json

PROMPT_PATH = Path(__file__).parent / "prompt.md"
SUMMARY_PROMPT = """你是图书结构分析师。用不超过 150 字概括这一章，必须依次覆盖四问：
1) 这章解决什么问题；2) 核心论点；3) 与前后章的关系（如信息不足可写“暂无法判断”）；
4) 内容性质（理论 / 案例 / 小结 / 附录）。只输出概括文字本身。"""

TASK = "outline_plan"
SUMMARY_TASK = "outline_summary"


class SplitPart(BaseModel):
    title: str
    start_chunk_id: int
    end_chunk_id: int


class PlanOp(BaseModel):
    op: Literal["exclude", "split", "merge", "organize", "group"]
    node_id: int | None = None
    node_ids: list[int] | None = None
    chapter_ids: list[int] | None = None
    title: str | None = None
    reason: str | None = None
    parts: list[SplitPart] | None = None


class PlanResult(BaseModel):
    thesis: str = Field(min_length=1, max_length=200)
    operations: list[PlanOp] = Field(default_factory=list)


def _system() -> str:
    return f"[TASK:{TASK}]\n" + PROMPT_PATH.read_text(encoding="utf-8")


async def summarize_chapter(db: Session, chapter_title: str, content: str) -> str:
    """逐章压缩摘要（四问模板，输入该章 refs 全文，技术方案 §5.2）。"""
    messages = [
        {"role": "system", "content": f"[TASK:{SUMMARY_TASK}]\n{SUMMARY_PROMPT}"},
        {
            "role": "user",
            "content": (
                f"章名：{chapter_title}\n\n```json\n"
                f"{json.dumps({'content': content}, ensure_ascii=False)}\n```"
            ),
        },
    ]
    scene: Scene = "outline"
    return (await complete(db, messages, scene=scene, temperature=0.1)).strip()


async def plan(db: Session, payload: dict[str, object]) -> str:
    """全书单次全局调用产出 thesis + 操作列表。"""
    messages = [
        {"role": "system", "content": _system()},
        {
            "role": "user",
            "content": "书籍结构与正文元数据如下（JSON）：\n\n```json\n"
            + json.dumps(payload, ensure_ascii=False, default=str)
            + "\n```",
        },
    ]
    scene: Scene = "outline"
    return await complete(db, messages, scene=scene, temperature=0.1)


def parse_plan(raw: str) -> PlanResult:
    data = extract_json(raw)
    return PlanResult.model_validate(data)
