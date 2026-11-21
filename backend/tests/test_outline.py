"""拟大纲（B2-03）：契约校验、冲突跳过、失败保树、恢复原目录、证据保护。"""

from __future__ import annotations

import pytest

from app.core.errors import Validation
from app.models import KnowledgePoint, Note, OutlineEvent
from app.services import knowledge, outline
from app.services.outline import PlanInvalid
from app.services.tree_core import TreeIndex
from app.skills.outline_planner import PlanOp, PlanResult, SplitPart
from tests.conftest import get_study


def _kp(db, name: str) -> KnowledgePoint:
    return db.query(KnowledgePoint).filter(KnowledgePoint.name == name).one()


def _input(db):
    study = get_study(db)
    return outline.build_plan_input(db, study.id, {})


def _apply(db, result: PlanResult, snapshot=None):
    study = get_study(db)
    if snapshot is None:
        _, snapshot = _input(db)
    return outline.apply_operations(db, study.id, result, snapshot)


async def test_auto_plan_ready_with_thesis(book) -> None:
    db = book
    study = get_study(db)
    status = await outline.run_planning(study.id)
    assert status == "ready"
    db.expire_all()
    study = get_study(db)
    assert study.outline_thesis
    # 桩规划给前两章建部分分组 → 出现 origin=ai_group 节点
    groups = [k for k in db.query(KnowledgePoint).all() if k.origin == "ai_group"]
    assert groups and groups[0].is_chapter is False


async def test_plan_failure_keeps_tree(book, monkeypatch) -> None:
    """结构化校验失败 → 整体失败保树（B2-03 反例）。"""
    from app.core.errors import LLMUnavailable

    async def boom(db, payload):
        raise LLMUnavailable("模型超时")

    from app.skills import outline_planner

    monkeypatch.setattr(outline_planner, "plan", boom)
    db = book
    study = get_study(db)
    before = sorted(k.name for k in db.query(KnowledgePoint).all())
    status = await outline.run_planning(study.id)
    assert status == "failed"
    db.expire_all()
    after = sorted(k.name for k in db.query(KnowledgePoint).all())
    assert before == after  # 原树保留
    assert "原目录未受影响" in (get_study(db).outline_error or "")


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
    """split 应用：原节点转容器（保 id），refs 迁移给子节点。"""
    db = book
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
    await outline.run_planning(study.id)  # 桩规划应用 group

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


def test_replan_conflict_409_and_missing_structure_422(book) -> None:
    import asyncio

    from app.core.errors import Conflict

    db = book
    study = get_study(db)
    study.outline_status = "planning"
    db.commit()
    with pytest.raises(Conflict):
        asyncio.run(outline.replan(db, study.id))
    study.outline_status = "idle"
    db.query(KnowledgePoint).delete()
    db.commit()
    with pytest.raises(Validation):
        asyncio.run(outline.replan(db, study.id))
