"""点亮与进度算法（技术方案 §12.1）：分母口径、三态、固定通过线、重考不灭灯。"""

from __future__ import annotations

import pytest

from app.models import KnowledgePoint
from app.services import knowledge
from app.services import quiz as quiz_service
from app.services.learning import get_or_create_session
from app.services.tree_core import TreeIndex
from tests.conftest import get_study


def _kp_by_name(db, name: str) -> KnowledgePoint:
    return db.query(KnowledgePoint).filter(KnowledgePoint.name == name).one()


def _unit_names(db) -> list[str]:
    study_id = get_study(db).id
    index = TreeIndex(db, study_id)
    return sorted(index.by_id[i].name for i in index.valid_units)


def test_valid_unit_and_progress_denominator(book) -> None:
    """结构叶 ∧ 未排除 ∧ refs≥1 才进分母；章有子节点是容器不进分母。"""
    db = book
    names = _unit_names(db)
    # 1.1/1.2/2.1/2.2 是叶子；第一章/第二章有子节点是容器；第三章无子节点是学习单元
    assert names == ["1.1 什么是 Agent", "1.2 Agent 的组成", "2.1 信息筛选", "2.2 信息压缩", "第三章 附录 习题答案"]
    index = TreeIndex(db, get_study(db).id)
    chapter1 = _kp_by_name(db, "第一章 Agent 导论")
    assert chapter1.id not in index.valid_units  # 容器（决策 #27）
    assert index.status_of(chapter1) is None


def test_excluding_all_children_keeps_parent_container(book) -> None:
    """排除全部子节点不得让父节点变成可学习单元（B2-06 反例）。"""
    db = book
    for name in ("1.1 什么是 Agent", "1.2 Agent 的组成"):
        knowledge.exclude(db, _kp_by_name(db, name).id, reason=None)
    chapter1 = _kp_by_name(db, "第一章 Agent 导论")
    index = TreeIndex(db, get_study(db).id)
    assert chapter1.id not in index.valid_units
    assert index.is_effectively_excluded(_kp_by_name(db, "1.1 什么是 Agent").id)


def test_progress_zero_denominator_shows_none(book) -> None:
    db = book
    index = TreeIndex(db, get_study(db).id)
    for kp in list(index.by_id.values()):
        if not kp.excluded:
            knowledge.exclude(db, kp.id, reason=None)
    fresh = TreeIndex(db, get_study(db).id)
    assert fresh.progress().total == 0
    assert fresh.progress().percent is None  # 分母 0 → null（B5-01）


def test_rename_does_not_change_denominator(book) -> None:
    db = book
    before = _unit_names(db)
    knowledge.rename(db, _kp_by_name(db, "1.1 什么是 Agent").id, "1.1 重命名后")
    after = _unit_names(db)
    assert sorted(n if n != "1.1 什么是 Agent" else "1.1 重命名后" for n in before) == after


async def test_pass_line_mapping_and_lighting(book) -> None:
    """3/4/5 题固定通过线；一次通过即点亮；简答不计分。"""
    db = book
    assert quiz_service.PASS_LINE == {3: 2, 4: 3, 5: 4}
    kp = _kp_by_name(db, "1.1 什么是 Agent")
    session = get_or_create_session(db, get_study(db).id, kp.id)
    q = await quiz_service.generate_quiz(db, session)
    assert q["graded_count"] == 4 and q["pass_line"] == 3

    # 全对 → passed 且点亮；简答练习给评语不计分
    answers = [
        {"no": 1, "choice": "B"}, {"no": 2, "choice": "C"},
        {"no": 3, "choice": False}, {"no": 4, "choice": False},
        {"no": 5, "text": "答了练习"},
    ]
    result = await quiz_service.answer_quiz(db, q["quiz_id"], answers)
    assert result["correct_count"] == 4 and result["passed"] is True
    db.expire_all()
    kp = _kp_by_name(db, "1.1 什么是 Agent")
    assert kp.lighted_at is not None
    assert kp.lighted_by_quiz_id == q["quiz_id"]
    short = next(x for x in result["per_question"] if not x["graded"])
    assert short.get("comment")  # 具体评语存在（桩）
    assert result["lighted"]["already_lighted"] is False


async def test_relight_not_triggered_by_failed_requiz(book) -> None:
    """已点亮后重考失败：原有点亮保留（B4-03 反例）。"""
    db = book
    kp = _kp_by_name(db, "1.2 Agent 的组成")
    session = get_or_create_session(db, get_study(db).id, kp.id)
    q1 = await quiz_service.generate_quiz(db, session)
    ok = [
        {"no": 1, "choice": "B"}, {"no": 2, "choice": "C"},
        {"no": 3, "choice": False}, {"no": 4, "choice": False},
        {"no": 5, "text": "x"},
    ]
    r1 = await quiz_service.answer_quiz(db, q1["quiz_id"], ok)
    assert r1["passed"] is True
    db.expire_all()
    first_lighted_at = _kp_by_name(db, "1.2 Agent 的组成").lighted_at
    first_evidence = _kp_by_name(db, "1.2 Agent 的组成").lighted_by_quiz_id

    q2 = await quiz_service.generate_quiz(db, session)  # 新一组（桩换题干）
    wrong = [
        {"no": 1, "choice": "A"}, {"no": 2, "choice": "A"},
        {"no": 3, "choice": True}, {"no": 4, "choice": True}, {"no": 5, "text": "y"},
    ]
    r2 = await quiz_service.answer_quiz(db, q2["quiz_id"], wrong)
    assert r2["passed"] is False
    assert r2["lighted"]["already_lighted"] is True
    db.expire_all()
    kp = _kp_by_name(db, "1.2 Agent 的组成")
    assert kp.lighted_at == first_lighted_at  # 不灭灯、不刷新
    assert kp.lighted_by_quiz_id == first_evidence


async def test_quiz_idempotent_generate_and_submit(book) -> None:
    """一节点一组进行中；生成与提交均幂等（P1-03）。"""
    db = book
    kp = _kp_by_name(db, "2.1 信息筛选")
    session = get_or_create_session(db, get_study(db).id, kp.id)
    q1 = await quiz_service.generate_quiz(db, session)
    q2 = await quiz_service.generate_quiz(db, session)
    assert q1["quiz_id"] == q2["quiz_id"]
    answers = [{"no": 1, "choice": "B"}, {"no": 2, "choice": "C"},
               {"no": 3, "choice": False}, {"no": 4, "choice": False}, {"no": 5, "text": "z"}]
    r1 = await quiz_service.answer_quiz(db, q1["quiz_id"], answers)
    r2 = await quiz_service.answer_quiz(db, q1["quiz_id"], answers)
    assert r2["quiz_id"] == r1["quiz_id"] and r2["passed"] == r1["passed"]
    assert r2["submitted_answers"] == r1["submitted_answers"]


async def test_unanswered_quiz_never_exposes_answers(book) -> None:
    """未提交测验公开面：任何响应不含答案（B4-01 反例）。"""
    import json

    db = book
    kp = _kp_by_name(db, "2.2 信息压缩")
    session = get_or_create_session(db, get_study(db).id, kp.id)
    q = await quiz_service.generate_quiz(db, session)
    blob = json.dumps(q, ensure_ascii=False, default=str)
    assert '"answer"' not in blob and '"explanation"' not in blob


async def test_duplicate_generation_fails_explicitly(book, monkeypatch) -> None:
    """二次仍完全重复 → 明确失败可重试，不下发旧题（B4-02 反例）。"""
    import json as json_mod

    from app.core.errors import LLMUnavailable
    from app.skills import quiz as quiz_skill

    db = book
    kp = _kp_by_name(db, "第三章 附录 习题答案")
    session = get_or_create_session(db, get_study(db).id, kp.id)
    first = await quiz_service.generate_quiz(db, session)
    # 提交第一组（全错，未通过）
    await quiz_service.answer_quiz(
        db, first["quiz_id"],
        [{"no": 1, "choice": "A"}, {"no": 2, "choice": "A"}, {"no": 3, "choice": True},
         {"no": 4, "choice": True}, {"no": 5, "text": "w"}],
    )

    async def fake_generate(db_, payload):
        # 永远返回与第一组完全相同的题干（最坏情况：桩完全不可用）
        out = []
        for qq in first["questions"]:
            item = {
                "no": qq["no"], "type": qq["type"], "graded": qq["graded"],
                "stem": qq["stem"], "options": qq.get("options"),
            }
            if qq["graded"]:
                item.update({"answer": "B" if qq["type"] == "choice" else True,
                             "explanation": "e", "refs": [1]})
            else:
                item["reference_answer"] = "r"
            out.append(item)
        return json_mod.dumps({"questions": out}, ensure_ascii=False)

    monkeypatch.setattr(quiz_skill, "generate", fake_generate)
    with pytest.raises(LLMUnavailable) as exc:
        await quiz_service.generate_quiz(db, session)
    assert "出题失败" in str(exc.value.detail)
