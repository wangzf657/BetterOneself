"""skills 契约（golden cases，LLM 全 mock）：outline_planner / tutor / quiz。"""

from __future__ import annotations

import json

import pytest

from app.core.llm import extract_json
from app.skills.outline_planner import parse_plan, summarize_chapter
from app.skills.outline_planner import plan as plan_skill
from app.skills.quiz import parse_quiz


def test_outline_parse_plan_valid() -> None:
    raw = json.dumps({
        "thesis": "一本关于结构的书。",
        "operations": [
            {"op": "exclude", "node_id": 9, "reason": "习题答案"},
            {"op": "split", "node_id": 4, "parts": [
                {"title": "上", "start_chunk_id": 10, "end_chunk_id": 20},
                {"title": "下", "start_chunk_id": 21, "end_chunk_id": 30}],
             "reason": "过粗"},
            {"op": "merge", "node_ids": [11, 12], "title": "合并"},
            {"op": "organize", "node_ids": [13, 14], "title": "区域"},
            {"op": "group", "chapter_ids": [1, 2], "title": "部分一"},
        ],
    }, ensure_ascii=False)
    result = parse_plan(raw)
    assert result.thesis == "一本关于结构的书。"
    assert [op.op for op in result.operations] == ["exclude", "split", "merge", "organize", "group"]


def test_outline_parse_plan_invalid_json() -> None:
    from app.core.errors import LLMError

    with pytest.raises(LLMError):
        parse_plan("完全不是 JSON 的输出")
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        parse_plan(json.dumps({"operations": []}))  # 缺 thesis


def test_outline_parse_plan_with_codefence() -> None:
    raw = "说明文字\n```json\n{\"thesis\": \"t\", \"operations\": []}\n```\n结尾"
    assert parse_plan(raw).thesis == "t"


async def test_outline_skill_payload_shape(db) -> None:
    payload = {
        "book_title": "T",
        "nodes": [{"id": 1, "name": "第1章", "parent_id": None, "level": 1,
                    "is_chapter": True, "char_count": 100, "subtree_char_count": 100,
                    "page_span": [1, 3], "excluded": False}],
        "chapter_summaries": {"1": "摘要"},
        "ref_manifest": [{"chunk_id": 1, "kp_id": 1, "order": 1, "title_path": "第1章",
                           "location": {"type": "lines", "line_start": 1, "line_end": 5},
                           "char_count": 100}],
    }
    raw = await plan_skill(db, payload)
    data = extract_json(raw)
    assert "thesis" in data and "operations" in data


async def test_chapter_summary_stub(db) -> None:
    text = await summarize_chapter(db, "第 1 章", "内容" * 100)
    assert "本章" in text or len(text) > 10


def test_quiz_parse_contract() -> None:
    raw = json.dumps({"questions": [
        {"no": 1, "type": "choice", "graded": True, "stem": "s1",
         "options": ["A. x", "B. y", "C. z", "D. w"], "answer": "B",
         "explanation": "e", "refs": [1], "dimension": "细节理解与辨析"},
        {"no": 2, "type": "judge", "graded": True, "stem": "s2", "answer": False,
         "explanation": "e", "refs": [2], "dimension": "应用"},
        {"no": 3, "type": "short", "graded": False, "stem": "s3", "reference_answer": "r"},
    ]}, ensure_ascii=False)
    draft = parse_quiz(raw)
    assert len(draft.questions) == 3
    assert draft.questions[0].answer == "B"
    assert draft.questions[2].graded is False


def test_tutor_prompt_contains_task_tag(db) -> None:
    from pathlib import Path

    prompt = (Path(__file__).resolve().parents[1] / "app/skills/tutor/prompt.md").read_text("utf-8")
    assert "学习方法" in prompt and "不改变" in prompt  # 方法只改陪学方式，不改通过线
    quiz_prompt = (Path(__file__).resolve().parents[1] / "app/skills/quiz/prompt.md").read_text("utf-8")
    assert "不计入成绩" in quiz_prompt and "history_stems" in quiz_prompt
    outline_prompt = (
        Path(__file__).resolve().parents[1] / "app/skills/outline_planner/prompt.md"
    ).read_text("utf-8")
    assert "连续" in outline_prompt and "章不可删" in outline_prompt
