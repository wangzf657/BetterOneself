"""确定性 LLM 桩（BO_LLM_STUB=1，E2E 与开发用）：不触网、不花 token。

skills 在系统提示首行带 [TASK:xxx] 标记，桩据此返回合法契约输出；
出题桩维护计数器，第二次生成换一套题干（覆盖「未通过再考不重复同题」E2E）。
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Sequence
from typing import Any

_quiz_counter = 0

_OPENING = (
    "本节在全书中的位置：它属于当前部分的核心推进，要解决的问题是——"
    "如何把零散材料组织成可用的结构。\n\n"
    "信息筛选的目标，是保留与当前任务直接相关的证据，而不是收集得越多越好；"
    "压缩也不是简单缩短文字，而是降低无关信息对注意力的干扰。[1][2]\n\n"
    "先想一想：如果把所有历史细节都放进上下文，为什么反而可能让回答更差？"
)

_CHAT = (
    "关键在于区分「相关」与「可用」：相关是静态相似，可用要服务当前任务。[1]\n\n"
    "建议回到原文这一段，对照你刚才的问题再看一遍，再自己复述一遍筛选标准。"
)

_COMMENT = (
    "你指出了问题的一部分，但还缺少「无关信息会分散注意力」这一层。"
    "建议从信噪比和当前任务相关性两个角度重新组织答案。"
)

_SUMMARY = (
    "本章解决什么问题：如何把原始材料变成结构化输入；核心论点：质量取决于筛选而非堆量；"
    "与前后章的关系：承上启下，为后续工程化铺路；内容性质：理论为主，含少量示例。"
)

_THESIS = "讲怎样把零散材料组织成可靠结构，按「基础—组织—工程化」三步推进。"


def _task(messages: Sequence[dict[str, str]]) -> str:
    for m in messages:
        if m.get("role") == "system":
            tag = re.search(r"\[TASK:([a-z_]+)\]", m.get("content", ""))
            if tag:
                return tag.group(1)
    return ""


def _payload(messages: Sequence[dict[str, str]]) -> dict[str, Any]:
    """提取用户消息里 ```json 围栏中的负载。"""
    for m in messages:
        if m.get("role") != "user":
            continue
        match = re.search(r"```json\r?\n(.*?)\r?\n```", m.get("content", ""), re.S)
        if match:
            try:
                data: dict[str, Any] = json.loads(match.group(1))
                return data
            except json.JSONDecodeError:
                continue
    return {}


def _chunk_ids(messages: Sequence[dict[str, str]]) -> list[int]:
    payload = _payload(messages)
    ids: list[int] = []
    for src in payload.get("sources", []):
        if isinstance(src, dict) and isinstance(src.get("chunk_id"), int):
            ids.append(src["chunk_id"])
    return ids


def _quiz_questions(messages: Sequence[dict[str, str]]) -> str:
    global _quiz_counter
    _quiz_counter += 1
    variant = _quiz_counter
    refs = [1]  # 契约：refs 为 sources 的 1 基编号（非 chunk_id）
    tag = "" if variant == 1 else f"（第 {variant} 组）"

    def q(no: int, **kw: object) -> dict[str, object]:
        return {"no": no, **kw}

    questions: list[dict[str, object]] = [
        q(
            1,
            type="choice",
            graded=True,
            stem=f"{tag}信息筛选的首要目标是？",
            options=[
                "A. 尽可能收集所有相关信息",
                "B. 保留与当前任务直接相关的证据",
                "C. 把原文逐字复制进上下文",
                "D. 优先保留最长的段落",
            ],
            answer="B",
            explanation="筛选以当前任务相关性为准，堆量会稀释信噪比。",
            refs=refs,
        ),
        q(
            2,
            type="choice",
            graded=True,
            stem=f"{tag}下列哪种做法最可能让回答变差？",
            options=[
                "A. 按任务相关性裁剪上下文",
                "B. 给信息标注来源",
                "C. 把全部历史消息原样放进上下文",
                "D. 分批按需取用资料",
            ],
            answer="C",
            explanation="无关信息会分散注意力、稀释关键证据。",
            refs=refs,
        ),
        q(
            3,
            type="judge",
            graded=True,
            stem=f"{tag}压缩上下文就是尽量把文字缩短。",
            answer=False,
            explanation="压缩的本质是降低无关信息干扰，不是机械缩写。",
            refs=refs,
        ),
        q(
            4,
            type="judge",
            graded=True,
            stem=f"{tag}与当前任务无关但主题相近的内容，也应当保留在上下文中。",
            answer=False,
            explanation="主题相近不等于任务相关，无关内容应裁剪。",
            refs=refs,
        ),
        q(
            5,
            type="short",
            graded=False,
            stem=f"{tag}为什么「把所有历史消息都放进上下文」通常会变差？",
            reference_answer="长上下文带来无关信息干扰，信噪比下降，模型注意力被稀释。",
        ),
    ]
    return json.dumps({"questions": questions}, ensure_ascii=False)


def _plan(messages: Sequence[dict[str, str]]) -> str:
    import os

    if os.environ.get("BO_STUB_OUTLINE_FAIL"):
        # E2E 专用：模拟「仅规划失败」——树保留，讲解测验不受影响（B2-03/B5-03）
        raise RuntimeError("stub: outline failed on purpose")
    payload = _payload(messages)
    nodes = payload.get("nodes", [])
    chapters = [
        n
        for n in nodes
        if isinstance(n, dict) and n.get("is_chapter") and not n.get("excluded") and n.get("level") == 1
    ]
    ops: list[dict[str, object]] = []
    if len(chapters) >= 2:
        ops.append(
            {
                "op": "group",
                "chapter_ids": [chapters[0]["id"], chapters[1]["id"]],
                "title": "第一部分（桩规划）",
                "reason": "前两章同属基础部分，按书的逻辑合并为一个部分（桩规划演示用）。",
            }
        )
    return json.dumps(
        {"thesis": _THESIS, "operations": ops}, ensure_ascii=False
    )


def complete(messages: Sequence[dict[str, str]], *, scene: str) -> str:
    task = _task(messages)
    if task == "outline_summary":
        return _SUMMARY
    if task == "outline_plan":
        return _plan(messages)
    if task == "quiz_gen":
        return _quiz_questions(messages)
    if task == "quiz_comment":
        return _COMMENT
    if task == "tutor_opening":
        return _OPENING
    if task == "tutor_chat":
        return _CHAT
    return "（桩）未识别的任务类型。"


async def stream(
    messages: Sequence[dict[str, str]], *, scene: str
) -> AsyncIterator[str]:
    text = complete(messages, scene=scene)
    for i in range(0, len(text), 12):
        yield text[i : i + 12]
