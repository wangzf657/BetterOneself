"""AI 规划（B2-03、B6-03/04）：契约校验、启动认领、建议暂存与逐条确认、冲突跳过、失败保树、证据保护。"""

from __future__ import annotations

import json

import pytest

from app.core.db import get_session_local
from app.core.errors import Conflict, Validation
from app.models import KnowledgePoint, Note, OutlineEvent, PlanningProposal, Source, Study
from app.services import knowledge, outline, pipeline
from app.services.learning import put_note
from app.services.outline import PlanInvalid
from app.services.tree_core import TreeIndex
from app.skills.outline_planner import PlanOp, PlanResult, SplitPart
from tests.conftest import get_study


def _kp(db, name: str) -> KnowledgePoint:
    return db.query(KnowledgePoint).filter(KnowledgePoint.name == name).one()


def _names(db) -> list[str]:
    return sorted(k.name for k in db.query(KnowledgePoint).all())


def _last_event(db, event_type: str) -> OutlineEvent:
    return (
        db.query(OutlineEvent).filter_by(event_type=event_type).order_by(OutlineEvent.id.desc()).first()
    )


def _input(db):
    study = get_study(db)
    return outline.build_plan_input(db, study.id, {})


def _apply(db, result: PlanResult, snapshot=None):
    study = get_study(db)
    if snapshot is None:
        _, snapshot = _input(db)
    return outline.apply_operations(db, study.id, result, snapshot)


async def _plan_to_confirm(db) -> dict:
    """走到 awaiting_confirm：precheck_ok → 消耗确认启动 → 生成并暂存建议。返回确认页视图。"""
    study = get_study(db)
    study.outline_status = "precheck_ok"
    db.commit()
    assert outline.start_planning(db, study.id, planned_days=12, learning_goal="先过一遍") == "planning"
    assert await outline.generate_proposal(study.id) == "awaiting_confirm"
    db.expire_all()
    view = outline.proposal_view(db, study.id)
    assert view is not None
    return view


async def test_generate_proposal_only_stages(book) -> None:
    """生成只暂存建议不改树；用户确认前 thesis 也不写（B6-03/04）。"""
    db = book
    before = _names(db)

    view = await _plan_to_confirm(db)

    study = get_study(db)
    assert study.outline_status == "awaiting_confirm" and study.outline_thesis is None
    assert _names(db) == before
    assert study.planned_days == 12 and study.learning_goal == "先过一遍"
    assert outline.build_plan_input(db, study.id, {})[0]["planning_context"] == {
        "planned_days": 12,
        "learning_goal": "先过一遍",
    }
    assert [op["op"] for op in view["operations"]] == ["group", "merge"]
    assert not any(op["flagged"] for op in view["operations"])
    proposed = _last_event(db, "planning_proposed")
    assert proposed.actor == "ai" and json.loads(proposed.detail_json or "{}") == {"planned": 2}


async def test_generate_reports_chapter_stage(book, monkeypatch) -> None:
    """章级进度：摘要阶段 x/y，结束后清掉（B6-05 验收 2）。"""
    db = book
    study = get_study(db)
    study.outline_status = "precheck_ok"
    db.commit()
    outline.start_planning(db, study.id, planned_days=10, learning_goal="g")
    seen: list = []
    real = outline.summarize_chapter

    async def spy(db_, name, content):
        seen.append(outline.planning_stage(study.id))
        return await real(db_, name, content)

    monkeypatch.setattr(outline, "summarize_chapter", spy)

    assert await outline.generate_proposal(study.id) == "awaiting_confirm"

    assert [(s["phase"], s["done"], s["total"]) for s in seen] == [
        ("summary", 0, 3),
        ("summary", 1, 3),
        ("summary", 2, 3),
    ]
    assert outline.planning_stage(study.id) is None


def test_start_planning_gates_and_claims_once(book) -> None:
    """未预检不能启动；双击/并发只有一次能认领 precheck_ok（B6-03）。"""
    db = book
    study = get_study(db)
    with pytest.raises(Conflict):
        outline.start_planning(db, study.id, planned_days=10, learning_goal="g")

    study.outline_status = "precheck_ok"
    db.commit()
    other = get_session_local()()
    other.get(Study, study.id)  # 另一请求也已读到 precheck_ok
    try:
        assert outline.start_planning(db, study.id, planned_days=10, learning_goal="g") == "planning"
        with pytest.raises(Conflict):
            outline.start_planning(other, study.id, planned_days=10, learning_goal="g")
    finally:
        other.close()
    db.expire_all()
    assert get_study(db).outline_status == "planning"
    assert db.query(OutlineEvent).filter_by(event_type="planning_started").count() == 1
    with pytest.raises(Conflict):
        outline.start_planning(db, study.id, planned_days=10, learning_goal="g")


async def test_start_with_pending_proposal_returns_to_confirm(book) -> None:
    """已有暂存建议：启动直接回确认页，不重花 token（B6-03）。"""
    db = book
    view = await _plan_to_confirm(db)
    study = get_study(db)
    study.outline_status = "precheck_ok"
    db.commit()
    starts = db.query(OutlineEvent).filter_by(event_type="planning_started").count()

    assert outline.start_planning(db, study.id, planned_days=30, learning_goal="g") == "awaiting_confirm"

    assert outline.proposal_view(db, study.id)["proposal_id"] == view["proposal_id"]
    assert db.query(OutlineEvent).filter_by(event_type="planning_started").count() == starts


async def test_plan_failure_keeps_tree(book, monkeypatch) -> None:
    """结构化校验失败 → 整体失败保树（B2-03 反例）；失败后可重新预检再规划。"""
    from app.core.errors import LLMUnavailable

    async def boom(db, payload):
        raise LLMUnavailable("模型超时")

    from app.skills import outline_planner

    monkeypatch.setattr(outline_planner, "plan", boom)
    db = book
    before = _names(db)
    study = get_study(db)
    study.outline_status = "precheck_ok"
    db.commit()
    outline.start_planning(db, study.id, planned_days=10, learning_goal="g")

    assert await outline.generate_proposal(study.id) == "failed"

    db.expire_all()
    study = get_study(db)
    assert _names(db) == before  # 原树保留
    assert "原目录未受影响" in (study.outline_error or "")
    assert study.outline_status in outline.PLAN_RETRYABLE
    assert outline.proposal_view(db, study.id) is None


async def test_evidence_flags_split_merge_only(book) -> None:
    """确认页预标注（B6-04 验收 2）：含证据的合并被标注；分组不因证据被标注。"""
    db = book
    put_note(db, _kp(db, "1.1 什么是 Agent").id, "笔记即学习证据")
    db.expire_all()

    view = await _plan_to_confirm(db)

    group, merge = view["operations"]
    assert group["flagged"] is False
    assert merge["targets"] == ["1.1 什么是 Agent", "1.2 Agent 的组成"]
    assert merge["flagged"] is True and merge["flag_reason"] == "子树含学习证据"


async def test_apply_selected_skips_flagged_and_finishes(book) -> None:
    """应用所选：被标注的条目即使硬选也在写事务内复查跳过，其余照常、状态 ready（B6-04）。"""
    db = book
    put_note(db, _kp(db, "1.1 什么是 Agent").id, "笔记即学习证据")
    db.expire_all()
    view = await _plan_to_confirm(db)
    study = get_study(db)
    pid = view["proposal_id"]

    with pytest.raises(Validation):
        outline.apply_proposal(db, study.id, pid, [])
    with pytest.raises(Validation):
        outline.apply_proposal(db, study.id, pid, [0, 0])
    with pytest.raises(Validation):
        outline.apply_proposal(db, study.id, pid, [2])

    result = outline.apply_proposal(db, study.id, pid, [0, 1])

    assert result["status"] == "ready" and result["skipped"][0]["reason"] == "学习证据"
    db.expire_all()
    study = get_study(db)
    assert study.outline_status == "ready" and study.outline_thesis
    assert _kp(db, "1.1 什么是 Agent") and _kp(db, "1.2 Agent 的组成")  # 合并被跳过
    assert db.query(KnowledgePoint).filter_by(origin="ai_group").count() == 1
    assert db.get(PlanningProposal, pid).status == "applied"
    finished = json.loads(_last_event(db, "planning_finished").detail_json or "{}")
    assert finished["adjust_summary"]["applied"] == 1 and finished["adjust_summary"]["skipped"] == 1
    assert finished["declined_by_user"] == []
    assert outline.proposal_view(db, study.id) is None
    with pytest.raises(Conflict):  # 已应用的建议不能再用
        outline.apply_proposal(db, study.id, pid, [0])


async def test_apply_records_what_user_left_out(book) -> None:
    """只选部分：未选的记入 declined_by_user，树只按所选改（B6-04）。"""
    db = book
    view = await _plan_to_confirm(db)
    study = get_study(db)
    before = _names(db)

    result = outline.apply_proposal(db, study.id, view["proposal_id"], [0])

    assert result["status"] == "ready" and result["skipped"] == []
    db.expire_all()
    assert _names(db) == sorted([*before, "第一部分（桩规划）"])  # 只有分组落地，合并未动
    finished = json.loads(_last_event(db, "planning_finished").detail_json or "{}")
    assert finished["declined_by_user"] == [1]


async def test_decline_keeps_tree(book) -> None:
    """全部拒绝：树保持原树、thesis 不写，记 planning_declined（B6-04 验收 4）。"""
    db = book
    view = await _plan_to_confirm(db)
    study = get_study(db)
    before = _names(db)

    assert outline.decline_proposal(db, study.id, view["proposal_id"]) == {"status": "skipped"}

    db.expire_all()
    study = get_study(db)
    assert study.outline_status == "skipped" and study.outline_thesis is None
    assert _names(db) == before
    assert db.get(PlanningProposal, view["proposal_id"]).status == "declined"
    declined = _last_event(db, "planning_declined")
    assert declined.actor == "user" and json.loads(declined.detail_json or "{}") == {"planned": 2}
    assert outline.proposal_view(db, study.id) is None
    with pytest.raises(Conflict):
        outline.decline_proposal(db, study.id, view["proposal_id"])


async def test_closing_dialog_keeps_proposal_and_detects_edits(book) -> None:
    """关闭确认页不走 decline：建议原样保留；期间的用户编辑被预标注并保护（B6-04.4）。"""
    db = book
    view = await _plan_to_confirm(db)
    study = get_study(db)
    pid = view["proposal_id"]
    knowledge.rename(db, _kp(db, "1.2 Agent 的组成").id, "1.2 已重命名")
    db.expire_all()

    view = outline.proposal_view(db, study.id)

    assert view["proposal_id"] == pid and get_study(db).outline_status == "awaiting_confirm"
    group, merge = view["operations"]
    assert group["flagged"] is False
    assert merge["flagged"] is True and merge["flag_reason"] == "建议生成后已被编辑"
    result = outline.apply_proposal(db, study.id, pid, [0, 1])  # 硬选：快照复查同样跳过
    assert result["skipped"][0]["reason"] == "用户编辑"
    assert _kp(db, "1.2 已重命名")


async def test_restore_original_supersedes_pending_proposal(book) -> None:
    """恢复原目录：待确认建议对着旧树，作废（B6-04）。"""
    db = book
    view = await _plan_to_confirm(db)
    study = get_study(db)

    knowledge.restore_original(db, study.id)

    db.expire_all()
    assert get_study(db).outline_status == "skipped"
    assert outline.proposal_view(db, study.id) is None
    assert db.get(PlanningProposal, view["proposal_id"]).status == "superseded"


async def test_reparse_supersedes_pending_proposal(book) -> None:
    db = book
    view = await _plan_to_confirm(db)
    study = get_study(db)
    source = db.get(Source, study.primary_source_id)
    source.parse_status = "failed"  # 重解析只在解析失败/无结构时可达
    db.commit()

    pipeline.reparse(db, source.id)

    assert db.get(PlanningProposal, view["proposal_id"]).status == "superseded"
    assert outline.proposal_view(db, study.id) is None


def test_validate_rejects_bad_ops(book) -> None:
    db = book
    payload, _ = _input(db)
    nodes = {n["name"]: n for n in payload["nodes"]}

    # 引用不存在的节点
    with pytest.raises(PlanInvalid):
        outline.validate_plan(
            PlanResult(thesis="t", operations=[PlanOp(op="exclude", node_id=99999, reason="r")]),
            payload,
        )
    # exclude 章锚点
    chapter = next(n for n in payload["nodes"] if n["is_chapter"])
    with pytest.raises(PlanInvalid):
        outline.validate_plan(
            PlanResult(thesis="t", operations=[PlanOp(op="exclude", node_id=chapter["id"], reason="r")]),
            payload,
        )
    # merge 非相邻
    a, b = nodes["1.1 什么是 Agent"], nodes["2.1 信息筛选"]
    with pytest.raises(PlanInvalid):
        outline.validate_plan(
            PlanResult(thesis="t", operations=[PlanOp(op="merge", node_ids=[a["id"], b["id"]], title="m")]),
            payload,
        )
    # group 不连续（第 1、3 章）
    chapters = [n for n in payload["nodes"] if n["is_chapter"]]
    with pytest.raises(PlanInvalid):
        outline.validate_plan(
            PlanResult(
                thesis="t",
                operations=[PlanOp(op="group", chapter_ids=[chapters[0]["id"], chapters[2]["id"]], title="g")],
            ),
            payload,
        )
    # 同一节点冲突操作
    leaf = nodes["1.1 什么是 Agent"]
    with pytest.raises(PlanInvalid):
        outline.validate_plan(
            PlanResult(
                thesis="t",
                operations=[
                    PlanOp(op="exclude", node_id=leaf["id"], reason="r"),
                    PlanOp(op="split", node_id=leaf["id"], parts=[
                        SplitPart(title="p1", start_chunk_id=1, end_chunk_id=1),
                        SplitPart(title="p2", start_chunk_id=2, end_chunk_id=2),
                    ]),
                ],
            ),
            payload,
        )


def test_split_partition_validation(book) -> None:
    """split 区间须完整、有序、不重叠、不跨节点（技术方案 §5.1）。"""
    db = book
    payload, _ = _input(db)
    leaf = next(n for n in payload["nodes"] if n["name"] == "1.1 什么是 Agent")
    chunk_ids = [m["chunk_id"] for m in payload["ref_manifest"] if m["kp_id"] == leaf["id"]]
    if len(chunk_ids) < 2:
        pytest.skip("样例书该节点切片不足 2 个")
    mid = len(chunk_ids) // 2
    ok = PlanResult(thesis="t", operations=[PlanOp(
        op="split", node_id=leaf["id"],
        parts=[SplitPart(title="前半", start_chunk_id=chunk_ids[0], end_chunk_id=chunk_ids[mid - 1]),
               SplitPart(title="后半", start_chunk_id=chunk_ids[mid], end_chunk_id=chunk_ids[-1])],
        reason="r")])
    outline.validate_plan(ok, payload)  # 合法分区通过

    bad = PlanResult(thesis="t", operations=[PlanOp(
        op="split", node_id=leaf["id"],
        parts=[SplitPart(title="只覆盖前半", start_chunk_id=chunk_ids[0], end_chunk_id=chunk_ids[mid - 1])],
        reason="r")])
    with pytest.raises(PlanInvalid):
        outline.validate_plan(bad, payload)  # 1 段且未覆盖全部 → 拒绝


def test_split_apply_makes_container_and_children(book) -> None:
    """split 应用：原节点转容器（保 id），refs 迁移给子节点，子节点继承原摘要。"""
    db = book
    db.get(KnowledgePoint, _kp(db, "2.1 信息筛选").id).chapter_summary = "摘要 S"
    db.commit()
    payload, snapshot = _input(db)
    leaf = next(n for n in payload["nodes"] if n["name"] == "2.1 信息筛选")
    chunk_ids = [m["chunk_id"] for m in payload["ref_manifest"] if m["kp_id"] == leaf["id"]]
    assert len(chunk_ids) >= 1
    result = PlanResult(thesis="t", operations=[PlanOp(
        op="split", node_id=leaf["id"],
        parts=[SplitPart(title="筛选 A", start_chunk_id=chunk_ids[0], end_chunk_id=chunk_ids[-1])],
        reason="过粗",
    )] if len(chunk_ids) == 1 else [PlanOp(
        op="split", node_id=leaf["id"],
        parts=[SplitPart(title="筛选 A", start_chunk_id=chunk_ids[0], end_chunk_id=chunk_ids[len(chunk_ids) // 2 - 1]),
               SplitPart(title="筛选 B", start_chunk_id=chunk_ids[len(chunk_ids) // 2], end_chunk_id=chunk_ids[-1])],
        reason="过粗",
    )])
    # 单段 split 不满足 2–5 → 先构造合法两段
    if len(chunk_ids) == 1:
        result = PlanResult(thesis="t", operations=[])  # 无法拆 → 跳过应用断言
        pytest.skip("样例切片不足")
    applied, skipped = _apply(db, result, snapshot)
    assert applied == ["split"] and not skipped
    db.expire_all()
    kp = _kp(db, "2.1 信息筛选")
    index = TreeIndex(db, get_study(db).id)
    assert index.children.get(kp.id)  # 转为容器
    children = index.children[kp.id]
    assert all(c.origin == "ai_split" for c in children)
    assert all(c.chapter_summary == "摘要 S" for c in children)


def test_merge_carries_summaries(book) -> None:
    """merge 应用：两份摘要拼接后按上限截断，写到新节点。

    写摘要后不过期就直接拍快照：带 tzinfo 的内存值不得被误判为「用户编辑」。
    """
    db = book
    a, b = _kp(db, "1.1 什么是 Agent"), _kp(db, "1.2 Agent 的组成")
    a.chapter_summary, b.chapter_summary = "甲", "乙"
    db.commit()
    _, snapshot = _input(db)

    applied, skipped = _apply(
        db, PlanResult(thesis="t", operations=[PlanOp(op="merge", node_ids=[a.id, b.id], title="1 合并")]),
        snapshot,
    )

    assert applied == ["merge"] and not skipped
    assert _kp(db, "1 合并").chapter_summary == "甲\n\n乙"

    c, d = _kp(db, "2.1 信息筛选"), _kp(db, "2.2 信息压缩")
    c.chapter_summary, d.chapter_summary = "丙" * 12000, "丁"
    db.commit()
    _, snapshot = _input(db)
    _apply(
        db, PlanResult(thesis="t", operations=[PlanOp(op="merge", node_ids=[c.id, d.id], title="2 合并")]),
        snapshot,
    )
    assert _kp(db, "2 合并").chapter_summary == "丙" * 12000


def test_user_edit_conflict_skips_op(book) -> None:
    """用户已编辑（updated_at 变化）→ 跳过该条并记 planning_conflict_skipped。"""
    db = book
    payload, snapshot = _input(db)  # 规划输入先拍快照
    leaf = next(n for n in payload["nodes"] if n["name"] == "1.2 Agent 的组成")
    knowledge.rename(db, leaf["id"], "1.2 已重命名")  # 规划期间用户编辑
    db.expire_all()
    result = PlanResult(thesis="t", operations=[PlanOp(op="exclude", node_id=leaf["id"], reason="r")])
    applied, skipped = _apply(db, result, snapshot)
    assert applied == [] and len(skipped) == 1
    assert skipped[0]["reason"] == "用户编辑"
    events = db.query(OutlineEvent).filter_by(event_type="planning_conflict_skipped").all()
    assert events


def test_evidence_blocks_split_merge(book) -> None:
    """目标子树有学习证据 → split/merge 跳过（决策 #29）。"""
    from app.services.learning import put_note

    db = book
    kp = _kp(db, "1.2 Agent 的组成")
    put_note(db, kp.id, "笔记即学习证据")
    db.expire_all()
    payload, snapshot = _input(db)
    target = next(n for n in payload["nodes"] if n["name"] == "1.2 Agent 的组成")
    chunk_ids = [m["chunk_id"] for m in payload["ref_manifest"] if m["kp_id"] == target["id"]]
    if len(chunk_ids) >= 2:
        result = PlanResult(thesis="t", operations=[PlanOp(
            op="split", node_id=target["id"],
            parts=[SplitPart(title="a", start_chunk_id=chunk_ids[0], end_chunk_id=chunk_ids[len(chunk_ids) // 2 - 1]),
                   SplitPart(title="b", start_chunk_id=chunk_ids[len(chunk_ids) // 2], end_chunk_id=chunk_ids[-1])],
            reason="r")])
        applied, skipped = _apply(db, result, snapshot)
        assert applied == [] and skipped and skipped[0]["reason"] == "学习证据"
    else:
        pytest.skip("切片不足")


async def test_restore_original_requires_no_evidence(book) -> None:
    """有任何学习证据 → 422 列证据节点；无证据 → 快照重建并撤销清单。"""
    from app.services.learning import put_note

    db = book
    study = get_study(db)
    view = await _plan_to_confirm(db)
    outline.apply_proposal(db, study.id, view["proposal_id"], [0])  # 应用桩规划的 group
    db.expire_all()
    study = get_study(db)

    # 有证据：笔记
    kp = _kp(db, "1.1 什么是 Agent")
    put_note(db, kp.id, "证据")
    preview = knowledge.restore_original_preview(db, study.id)
    assert preview["can_restore"] is False and preview["evidence_kps"]
    with pytest.raises(Validation):
        knowledge.restore_original(db, study.id)

    # 移除证据（无删除笔记 API——直接清表模拟“从未学习”）
    db.query(Note).delete()
    db.commit()
    before = sorted(k.name for k in db.query(KnowledgePoint).all())
    result = knowledge.restore_original(db, study.id)
    db.expire_all()
    after = sorted(k.name for k in db.query(KnowledgePoint).all())
    assert before != after  # AI 分组被撤销
    assert result["restored"] == len(after)
    index = TreeIndex(db, study.id)
    assert all(k.origin in ("toc", "heading") for k in index.kps)
    assert db.query(PlanningProposal).filter_by(study_id=study.id).first().status == "applied"
