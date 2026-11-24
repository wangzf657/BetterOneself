"""AI 规划服务（B2-03、B6-03/04，决策 #25/#34）：生成 → 代码校验 → 暂存建议 → 用户确认后应用。

- 章摘要先行（失败退回仅结构信息输入）；
- 生成：thesis + 五类操作单次全局调用，结果只暂存不应用（planning_proposals）；
- 校验：任一不满足 → 整体失败保树（宁缺毋滥）；
- 应用：用户逐条勾选后在写事务内逐条复查（用户编辑 / 学习证据），跳过记 planning_conflict_skipped。
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.core.db import get_session_local
from app.core.errors import Conflict, LLMError, NotFound, Validation
from app.core.security import sanitize_error
from app.models import (
    KnowledgePoint,
    KnowledgeRef,
    OutlineEvent,
    PlanningProposal,
    Source,
    SourceChunk,
    Study,
    utcnow,
)
from app.services.events import record_event
from app.services.tree_core import TreeIndex, subtree_has_evidence
from app.skills.outline_planner import PlanOp, PlanResult, summarize_chapter

logger = logging.getLogger(__name__)

CHAPTER_SUMMARY_CHAR_CAP = 12000
PLAN_ERROR_PREFIX = "AI 规划未完成"
K_CN = 1.2  # 中文 token/字的估算系数（V0.1.1 技术设计 §4）
SUMMARY_OUTPUT_TOKENS = 300  # 每章摘要的输出估计
SUMMARY_CHARS = 150  # 单章摘要字数上限（skill 提示词约定）
PLAN_OUTPUT_TOKENS = 2000
# 可重新进入规划的状态；planning / awaiting_confirm 是进行中或等用户处理
PLAN_RETRYABLE = ("structure_ready", "precheck_failed", "failed", "skipped", "ready")


class PlanInvalid(Exception):
    """结构化校验失败——本次规划整体失败保树。"""


_stage_lock = threading.Lock()
_stage: dict[int, dict[str, object]] = {}  # study_id → {phase, done, total}，只活在进程内


def _set_stage(study_id: int, phase: str, done: int, total: int) -> None:
    with _stage_lock:
        _stage[study_id] = {"phase": phase, "done": done, "total": total}


def planning_stage(study_id: int) -> dict[str, object] | None:
    with _stage_lock:
        return dict(_stage[study_id]) if study_id in _stage else None


def _pending_proposal(db: Session, study_id: int) -> PlanningProposal | None:
    return (
        db.query(PlanningProposal)
        .filter(PlanningProposal.study_id == study_id, PlanningProposal.status == "pending")
        .one_or_none()
    )


def start_planning(
    db: Session, study_id: int, *, planned_days: int, learning_goal: str
) -> str:
    """消耗确认后的启动（B6-03）：precheck_ok → planning；返回新状态，后台任务由调用方起。"""
    study = db.get(Study, study_id)
    if study is None:
        raise NotFound("学习项目不存在")
    status = study.outline_status
    if status == "planning":
        raise Conflict("AI 规划正在进行中，请稍候")
    if status == "awaiting_confirm":
        raise Conflict("已有待确认的规划建议，请先确认或拒绝")
    if status != "precheck_ok":
        raise Conflict("预检尚未通过，请先完成预检")
    # 上次生成完就中断：建议还在，直接回到确认，不重花 token
    target = "awaiting_confirm" if _pending_proposal(db, study_id) is not None else "planning"
    # 条件更新原子认领：双击或并发请求只有一个能把 precheck_ok 换走
    claimed = cast(
        CursorResult[Any],
        db.execute(
            update(Study)
            .where(Study.id == study_id, Study.outline_status == "precheck_ok")
            .values(
                outline_status=target,
                outline_error=None,
                planned_days=planned_days,
                learning_goal=learning_goal,
            )
        ),
    ).rowcount
    if not claimed:
        raise Conflict("AI 规划状态已变化，请刷新后重试")
    if target == "planning":
        record_event(db, study_id, "planning_started", "ai")
    db.commit()
    return target


async def generate_proposal(study_id: int) -> str:
    """后台规划任务：章摘要 → 全局规划 → 校验 → 暂存建议 → awaiting_confirm。返回最终 outline_status。"""
    db = get_session_local()()
    try:
        study = db.get(Study, study_id)
        if study is None or study.outline_status != "planning":
            return study.outline_status if study else "idle"
        try:
            chapters = sum(1 for kp in TreeIndex(db, study_id).kps if kp.is_chapter)
            _set_stage(study_id, "summary", 0, chapters)
            summaries = await _summarize_chapters(
                db, study_id, on_progress=lambda done, total: _set_stage(study_id, "summary", done, total)
            )
            input_data, snapshot = build_plan_input(db, study_id, summaries)
            from app.skills.outline_planner import parse_plan
            from app.skills.outline_planner import plan as skill_plan

            _set_stage(study_id, "plan", 0, 1)
            result = parse_plan(await skill_plan(db, input_data))
            validate_plan(result, input_data)

            db.add(
                PlanningProposal(
                    study_id=study_id,
                    thesis=result.thesis,
                    ops_json=json.dumps(
                        {"operations": [op.model_dump() for op in result.operations], "snapshot": snapshot},
                        ensure_ascii=False,
                    ),
                )
            )
            study.outline_status = "awaiting_confirm"
            study.outline_error = None
            record_event(
                db, study_id, "planning_proposed", "ai", detail={"planned": len(result.operations)}
            )
            db.commit()
            return "awaiting_confirm"
        except (PlanInvalid, Validation, LLMError) as e:
            reason = str(e)
        except Exception as e:
            logger.exception("AI 规划内部错误 study=%s", study_id)
            reason = sanitize_error(e)
        db.rollback()
        assert study is not None
        study.outline_status = "failed"
        study.outline_error = f"{PLAN_ERROR_PREFIX}（仅规划失败，原目录未受影响）：{reason}"
        record_event(db, study_id, "planning_failed", "ai", detail={"reason": reason})
        db.commit()
        return "failed"
    finally:
        with _stage_lock:
            _stage.pop(study_id, None)
        db.close()


def embedding_tokens(total_chars: int) -> int:
    return int(total_chars * K_CN)


def planning_token_range(chapter_chars: list[int], plan_input_chars: int) -> list[int]:
    """AI 规划 token 区间 [下限, 上限]：摘要输入/输出 + 规划输入/输出（V0.1.1 技术设计 §4）。"""
    total = (
        sum(min(c, CHAPTER_SUMMARY_CHAR_CAP) for c in chapter_chars) * K_CN
        + len(chapter_chars) * SUMMARY_OUTPUT_TOKENS
        + plan_input_chars * K_CN
        + PLAN_OUTPUT_TOKENS
    )
    return [int(total * 0.9), int(total * 1.3)]


def estimate_tokens(db: Session, study_id: int) -> dict[str, Any]:
    """消耗预估（B6-03）：全部由已落库数据静态计算，不调用任何 API。"""
    study = db.get(Study, study_id)
    if study is None:
        raise NotFound("学习项目不存在")
    source = db.get(Source, study.primary_source_id) if study.primary_source_id else None
    embed_chars = (
        sum(c.char_count for c in db.query(SourceChunk).filter(SourceChunk.source_id == source.id))
        if source is not None
        else 0
    )
    payload, _ = build_plan_input(db, study_id, {})
    # 没有正文引用的章不进摘要
    chapters = [n["subtree_char_count"] for n in payload["nodes"] if n["is_chapter"]]
    chapters = [c for c in chapters if c > 0]
    plan_input_chars = (
        len(json.dumps(payload, ensure_ascii=False, default=str)) + len(chapters) * SUMMARY_CHARS
    )
    return {
        "embedding_tokens": embedding_tokens(embed_chars),
        "planning_tokens": planning_token_range(chapters, plan_input_chars),
    }


def _op_target_ids(op: dict[str, Any]) -> list[int]:
    if op.get("node_id") is not None:
        return [int(op["node_id"])]
    ids = op.get("node_ids") or op.get("chapter_ids") or []
    return [int(i) for i in ids]


def _load_ops(proposal: PlanningProposal) -> tuple[list[dict[str, Any]], dict[int, str]]:
    """JSON 落库后键是字符串，快照键要转回节点 id 才能比对。"""
    data = json.loads(proposal.ops_json)
    return data["operations"], {int(k): v for k, v in data["snapshot"].items()}


def _stamp(dt: datetime) -> str:
    """编辑比对的规范串：SQLite 读回的是 naive UTC，刚写入未过期的对象带 tzinfo，两种形态要可比。"""
    return (dt.astimezone(UTC).replace(tzinfo=None) if dt.tzinfo else dt).isoformat()


def _flag_reason(
    db: Session,
    study_id: int,
    index: TreeIndex,
    op: dict[str, Any],
    snapshot: dict[int, str],
) -> str | None:
    """确认页预标注；规则与 apply_operations 的复查一致（B6-04 验收 2）。"""
    found = [index.by_id.get(i) for i in _op_target_ids(op)]
    if any(k is None for k in found):
        return "节点已不存在"
    kps = [k for k in found if k is not None]
    if any(k.id in snapshot and snapshot[k.id] != _stamp(k.updated_at) for k in kps):
        return "建议生成后已被编辑"
    kind = op["op"]
    if kind == "exclude" and kps[0].is_chapter:
        return "章锚点不可排除"
    if kind == "split":
        if index.children.get(kps[0].id):
            return "目标已有子节点"
        if not index.refs_count.get(kps[0].id):
            return "目标没有正文引用"
        if subtree_has_evidence(db, study_id, index.subtree_ids(kps[0].id)):
            return "子树含学习证据"
    if kind == "merge":
        if index.children.get(kps[0].id) or index.children.get(kps[1].id):
            return "目标已有子节点"
        if subtree_has_evidence(db, study_id, index.subtree_ids(kps[0].id) | index.subtree_ids(kps[1].id)):
            return "子树含学习证据"
    return None


def proposal_view(db: Session, study_id: int) -> dict[str, Any] | None:
    """当前待确认建议（含逐条预标注）；没有待确认的返回 None。"""
    study = db.get(Study, study_id)
    if study is None:
        raise NotFound("学习项目不存在")
    proposal = _pending_proposal(db, study_id)
    if proposal is None:
        return None
    ops, snapshot = _load_ops(proposal)
    index = TreeIndex(db, study_id)
    items: list[dict[str, Any]] = []
    for op in ops:
        flag = _flag_reason(db, study_id, index, op, snapshot)
        items.append(
            {
                **op,
                "targets": [index.by_id[i].name if i in index.by_id else f"#{i}" for i in _op_target_ids(op)],
                "flagged": flag is not None,
                "flag_reason": flag,
            }
        )
    return {
        "proposal_id": proposal.id,
        "thesis": proposal.thesis,
        "created_at": proposal.created_at,
        "operations": items,
    }


def _proposal_to_apply(
    db: Session, study: Study, proposal_id: int
) -> tuple[PlanningProposal, list[dict[str, Any]], dict[int, str]]:
    if study.outline_status != "awaiting_confirm":
        raise Conflict("当前没有待确认的规划建议")
    proposal = db.get(PlanningProposal, proposal_id)
    if proposal is None or proposal.study_id != study.id or proposal.status != "pending":
        raise Conflict("该规划建议已失效，请刷新后重试")
    ops, snapshot = _load_ops(proposal)
    return proposal, ops, snapshot


def apply_proposal(db: Session, study_id: int, proposal_id: int, selected: list[int]) -> dict[str, Any]:
    """应用用户勾选的操作子集（B6-04）；写事务内仍逐条复查，冲突的跳过并记事件。"""
    study = db.get(Study, study_id)
    if study is None:
        raise NotFound("学习项目不存在")
    proposal, ops, snapshot = _proposal_to_apply(db, study, proposal_id)
    if not selected:
        raise Validation("请至少选择一条操作，或选择全部拒绝")
    if len(set(selected)) != len(selected) or any(i < 0 or i >= len(ops) for i in selected):
        raise Validation("所选操作序号无效")

    result = PlanResult(
        thesis=proposal.thesis or "", operations=[PlanOp.model_validate(ops[i]) for i in selected]
    )
    applied, skipped = apply_operations(db, study_id, result, snapshot)

    db.expire_all()
    study = db.get(Study, study_id)
    applied_row = db.get(PlanningProposal, proposal_id)
    assert study is not None and applied_row is not None
    study.outline_thesis = result.thesis
    study.outline_status = "ready"
    study.outline_error = None
    applied_row.status = "applied"
    applied_row.applied_at = utcnow()
    adjust = _adjust_summary(
        PlanResult(
            thesis=result.thesis, operations=[PlanOp.model_validate(op) for op in ops]
        ),
        applied,
        skipped,
    )

    record_event(
        db,
        study_id,
        "planning_finished",
        "ai",
        detail={
            "adjust_summary": adjust,
            "declined_by_user": [i for i in range(len(ops)) if i not in selected],
        },
    )
    db.commit()
    return {"status": "ready", "adjust_summary": adjust, "skipped": skipped}


def decline_proposal(db: Session, study_id: int, proposal_id: int) -> dict[str, Any]:
    """全部拒绝：树保持原树（B6-04 验收 4）。关闭确认页不走这里，建议原样保留。"""
    study = db.get(Study, study_id)
    if study is None:
        raise NotFound("学习项目不存在")
    proposal, ops, _ = _proposal_to_apply(db, study, proposal_id)
    proposal.status = "declined"
    study.outline_status = "skipped"
    study.outline_error = None
    record_event(db, study_id, "planning_declined", "user", detail={"planned": len(ops)})
    db.commit()
    return {"status": "skipped"}


def supersede_pending(db: Session, study_id: int) -> None:
    """树被整体重置（恢复原目录 / 重解析）：待确认建议对着旧树，作废。"""
    db.execute(
        update(PlanningProposal)
        .where(PlanningProposal.study_id == study_id, PlanningProposal.status == "pending")
        .values(status="superseded")
    )


async def _summarize_chapters(
    db: Session, study_id: int, *, on_progress: Callable[[int, int], None] | None = None
) -> dict[int, str]:
    """逐章摘要（四问模板）；写 kp.chapter_summary 不触发 updated_at；单章失败跳过。"""
    index = TreeIndex(db, study_id)
    chapters = [k for k in index.kps if k.is_chapter]
    summaries: dict[int, str] = {}
    for done, ch in enumerate(chapters, start=1):
        if on_progress is not None:
            on_progress(done - 1, len(chapters))
        chunk_ids: list[int] = []
        for kid in index.subtree_ids(ch.id):
            rows = (
                db.query(KnowledgeRef.chunk_id)
                .filter(KnowledgeRef.kp_id == kid)
                .order_by(KnowledgeRef.sort_order)
                .all()
            )
            chunk_ids.extend(r[0] for r in rows)
        if not chunk_ids:
            continue
        chunks = (
            db.query(SourceChunk)
            .filter(SourceChunk.id.in_(chunk_ids))
            .order_by(SourceChunk.sort_order)
            .all()
        )
        content = "\n\n".join(c.content for c in chunks)[:CHAPTER_SUMMARY_CHAR_CAP]
        try:
            summary = await summarize_chapter(db, ch.name, content)
        except Exception:
            logger.warning("章节摘要失败 chapter=%s", ch.id)
            continue
        db.execute(
            update(KnowledgePoint)
            .where(KnowledgePoint.id == ch.id)
            .values(chapter_summary=summary, updated_at=KnowledgePoint.updated_at)
        )
        db.commit()
        summaries[ch.id] = summary
        if on_progress is not None:
            on_progress(done, len(chapters))
    return summaries


def build_plan_input(
    db: Session, study_id: int, summaries: dict[int, str]
) -> tuple[dict[str, Any], dict[int, str]]:
    """构造 skill 输入（含 char_count / subtree_char_count / page_span / ref manifest）。"""
    study = db.get(Study, study_id)
    assert study is not None
    index = TreeIndex(db, study_id)
    depth: dict[int, int] = {}

    def walk(kp_id: int | None, level: int) -> None:
        for child in index.children.get(kp_id, []):
            depth[child.id] = level
            walk(child.id, level + 1)

    walk(None, 1)

    own_chars: dict[int, int] = {}
    for ref in db.query(KnowledgeRef).all():
        if ref.kp_id in index.by_id:
            own_chars.setdefault(ref.kp_id, 0)
    chunk_chars = {c.id: c.char_count for c in db.query(SourceChunk).all()}
    chunk_locs = {c.id: c.location for c in db.query(SourceChunk).all()}
    kp_id_set = set(index.by_id.keys())
    for ref in db.query(KnowledgeRef).filter(KnowledgeRef.kp_id.in_(kp_id_set)).all():
        own_chars[ref.kp_id] = own_chars.get(ref.kp_id, 0) + chunk_chars.get(ref.chunk_id, 0)

    nodes: list[dict[str, Any]] = []
    for kp in index.kps:
        subtree_ids = index.subtree_ids(kp.id)
        sub_chunks: set[int] = set()
        pages: list[int] = []
        for kid in subtree_ids:
            for ref in db.query(KnowledgeRef).filter(KnowledgeRef.kp_id == kid).all():
                sub_chunks.add(ref.chunk_id)
                loc = chunk_locs.get(ref.chunk_id)
                if loc:
                    try:
                        d = json.loads(loc)
                        if d.get("type") == "pdf":
                            pages.extend(
                                [d.get("page_start"), d.get("page_end")]
                            )
                    except json.JSONDecodeError:
                        pass
        page_span = (
            [min(p for p in pages if p is not None), max(p for p in pages if p is not None)]
            if pages
            else None
        )
        nodes.append(
            {
                "id": kp.id,
                "name": kp.name,
                "parent_id": kp.parent_id,
                "level": depth.get(kp.id, 1),
                "is_chapter": kp.is_chapter,
                "char_count": own_chars.get(kp.id, 0),
                "subtree_char_count": sum(chunk_chars.get(c, 0) for c in sub_chunks),
                "page_span": page_span,
                "excluded": kp.excluded,
            }
        )

    manifest = (
        db.query(KnowledgeRef, SourceChunk)
        .join(SourceChunk, SourceChunk.id == KnowledgeRef.chunk_id)
        .filter(KnowledgeRef.kp_id.in_(kp_id_set))
        .order_by(SourceChunk.sort_order)
        .all()
    )
    ref_manifest = [
        {
            "chunk_id": chunk.id,
            "kp_id": ref.kp_id,
            "order": chunk.sort_order,
            "title_path": chunk.level_path,
            "location": json.loads(chunk.location),
            "char_count": chunk.char_count,
        }
        for ref, chunk in manifest
    ]
    chapter_summaries = {str(k): v for k, v in summaries.items()}
    payload = {
        "book_title": study.name,
        "nodes": nodes,
        "chapter_summaries": chapter_summaries or None,
        "ref_manifest": ref_manifest,
        # 只作规划上下文（B6-03）：不生成学习计划或排期
        "planning_context": {"planned_days": study.planned_days, "learning_goal": study.learning_goal},
    }
    snapshot = {kp.id: _stamp(kp.updated_at) for kp in index.kps}
    return payload, snapshot


def _chapter_ancestor(index: TreeIndex, kp_id: int) -> int | None:
    cur: KnowledgePoint | None = index.by_id.get(kp_id)
    while cur is not None:
        if cur.is_chapter:
            return cur.id
        cur = index.by_id.get(cur.parent_id) if cur.parent_id else None
    return None


def _ordered_chunk_ids(db: Session, kp_id: int) -> list[int]:
    rows = (
        db.query(KnowledgeRef.chunk_id, SourceChunk.sort_order)
        .join(SourceChunk, SourceChunk.id == KnowledgeRef.chunk_id)
        .filter(KnowledgeRef.kp_id == kp_id)
        .order_by(SourceChunk.sort_order)
        .all()
    )
    return [r[0] for r in rows]


def validate_plan(result: PlanResult, input_data: dict[str, Any]) -> None:
    """代码层校验（§5.4）；任一失败 → 整体失败保树。"""
    nodes = {n["id"]: n for n in input_data["nodes"]}
    children: dict[int | None, list[dict[str, Any]]] = {}
    for n in input_data["nodes"]:
        children.setdefault(n["parent_id"], []).append(n)
    for lst in children.values():
        lst.sort(key=lambda n: n["id"])  # 建树序即书内序（parse 时写入）

    if not result.thesis.strip() or len(result.thesis) > 200:
        raise PlanInvalid("总述为空或过长")

    used: dict[int, str] = {}
    for op in result.operations:
        if op.op == "exclude":
            if op.node_id is None or op.node_id not in nodes:
                raise PlanInvalid(f"exclude 引用了不存在的节点 {op.node_id}")
            if nodes[op.node_id]["is_chapter"]:
                raise PlanInvalid(f"exclude 不得作用于章锚点（{nodes[op.node_id]['name']}）")
            if not (op.reason and op.reason.strip()):
                raise PlanInvalid("exclude 必须给理由")
            _mark_conflict(used, op.node_id, "exclude")
        elif op.op == "split":
            if op.node_id is None or op.node_id not in nodes:
                raise PlanInvalid(f"split 引用了不存在的节点 {op.node_id}")
            node = nodes[op.node_id]
            if children.get(op.node_id):
                raise PlanInvalid(f"split 目标不是结构叶：{node['name']}")
            if node["char_count"] <= 0:
                raise PlanInvalid(f"split 目标没有正文引用：{node['name']}")
            parts = op.parts or []
            if not (2 <= len(parts) <= 5):
                raise PlanInvalid(f"split 产物须为 2–5 段：{node['name']}")
            expect = [
                m["chunk_id"]
                for m in input_data["ref_manifest"]
                if m["kp_id"] == op.node_id
            ]
            got: list[int] = []
            for p in parts:
                if not (p.title and p.title.strip()):
                    raise PlanInvalid("split 段缺少标题")
                got.extend([p.start_chunk_id, p.end_chunk_id])
            # 区间首尾相接、完整覆盖、互不重叠
            expanded: list[int] = []
            for p in parts:
                if p.start_chunk_id not in expect or p.end_chunk_id not in expect:
                    raise PlanInvalid(f"split 区间引用了其他节点的切片：{node['name']}")
                si, ei = expect.index(p.start_chunk_id), expect.index(p.end_chunk_id)
                if si > ei:
                    raise PlanInvalid(f"split 区间顺序错误：{node['name']}")
                expanded.extend(expect[si : ei + 1])
            if expanded != expect:
                raise PlanInvalid(f"split 区间未完整覆盖该节点全部切片：{node['name']}")
            _mark_conflict(used, op.node_id, "split")
        elif op.op == "merge":
            ids = op.node_ids or []
            if len(ids) != 2 or any(i not in nodes for i in ids):
                raise PlanInvalid("merge 需要恰好两个存在的节点")
            a, b = nodes[ids[0]], nodes[ids[1]]
            for n in (a, b):
                if children.get(n["id"]):
                    raise PlanInvalid(f"merge 目标不是结构叶：{n['name']}")
            if a["parent_id"] != b["parent_id"]:
                raise PlanInvalid("merge 双方必须同父")
            sibs = sorted(children.get(a["parent_id"], []), key=lambda n: n["id"])
            pos = [n["id"] for n in sibs]
            if abs(pos.index(a["id"]) - pos.index(b["id"])) != 1:
                raise PlanInvalid("merge 双方必须相邻")
            if not (op.title and op.title.strip()):
                raise PlanInvalid("merge 缺少新标题")
            _mark_conflict(used, ids[0], "merge")
            _mark_conflict(used, ids[1], "merge")
        elif op.op == "organize":
            ids = op.node_ids or []
            if len(ids) < 2 or any(i not in nodes for i in ids):
                raise PlanInvalid("organize 需要至少两个存在的节点")
            parents = {nodes[i]["parent_id"] for i in ids}
            if len(parents) != 1:
                raise PlanInvalid("organize 目标必须同父")
            sibs = sorted(children.get(parents.pop(), []), key=lambda n: n["id"])
            pos = [n["id"] for n in sibs]
            idxs = sorted(pos.index(i) for i in ids)
            if idxs != list(range(idxs[0], idxs[0] + len(idxs))):
                raise PlanInvalid("organize 目标必须连续")
            if not (op.title and op.title.strip()):
                raise PlanInvalid("organize 缺少标题")
            for i in ids:
                _mark_conflict(used, i, "organize")
        elif op.op == "group":
            ids = op.chapter_ids or []
            if len(ids) < 2 or any(i not in nodes for i in ids):
                raise PlanInvalid("group 需要至少两个存在的章")
            for i in ids:
                if not nodes[i]["is_chapter"]:
                    raise PlanInvalid(f"group 目标不是章：{nodes[i]['name']}")
                if nodes[i]["parent_id"] is not None:
                    raise PlanInvalid("group 仅作用于顶层章")
            tops = sorted(
                [n for n in input_data["nodes"] if n["parent_id"] is None],
                key=lambda n: n["id"],
            )
            chapters_top = [n["id"] for n in tops if n["is_chapter"]]
            idxs = sorted(chapters_top.index(i) for i in ids)
            if idxs != list(range(idxs[0], idxs[0] + len(idxs))):
                raise PlanInvalid("group 必须覆盖连续章节区间")
            if not (op.title and op.title.strip()):
                raise PlanInvalid("group 缺少标题")
            for i in ids:
                _mark_conflict(used, i, "group")


def _mark_conflict(used: dict[int, str], node_id: int, op_name: str) -> None:
    if node_id in used:
        raise PlanInvalid(f"节点 {node_id} 同时出现在 {used[node_id]} 与 {op_name} 中")
    used[node_id] = op_name


def _renumber_children(db: Session, parent_id: int | None) -> None:
    kids = (
        db.query(KnowledgePoint)
        .filter(KnowledgePoint.parent_id == parent_id if parent_id is not None
                else KnowledgePoint.parent_id.is_(None))
        .order_by(KnowledgePoint.sort_order, KnowledgePoint.id)
        .all()
    )
    for i, kid in enumerate(kids, start=1):
        kid.sort_order = i


def _progress_dict(index: TreeIndex) -> dict[str, Any]:
    p = index.progress()
    return p.as_dict() if p.total else {"lighted": 0, "total": 0, "percent": None}


def apply_operations(
    db: Session, study_id: int, result: PlanResult, snapshot: dict[int, str]
) -> tuple[list[str], list[dict[str, Any]]]:
    """逐条在写事务内复查（用户编辑 / 学习证据）；任一冲突只跳过该条不失败整次。"""
    applied: list[str] = []
    skipped: list[dict[str, Any]] = []

    def edited(kp: KnowledgePoint) -> bool:
        snap = snapshot.get(kp.id)
        return snap is not None and _stamp(kp.updated_at) != snap

    def skip(op_name: str, kp: KnowledgePoint | None, reason: str) -> None:
        skipped.append(
            {"op": op_name, "kp_id": kp.id if kp else None,
             "kp_name": kp.name if kp else None, "reason": reason}
        )
        record_event(
            db, study_id, "planning_conflict_skipped", "ai", kp_id=kp.id if kp else None,
            detail={"op": op_name, "reason": reason}, kp_name=kp.name if kp else None,
        )
        db.commit()

    for op in result.operations:
        try:
            db.expire_all()
            index = TreeIndex(db, study_id)
            if op.op == "exclude":
                kp = db.get(KnowledgePoint, op.node_id or -1)
                if kp is None or kp.study_id != study_id:
                    skip("exclude", None, "节点不存在")

                    continue
                if kp.is_chapter:
                    skip("exclude", kp, "章锚点不可排除")

                    continue
                if edited(kp):
                    skip("exclude", kp, "用户编辑")

                    continue
                before = _progress_dict(index)
                kp.excluded = True
                kp.planning_note = op.reason
                db.commit()
                after_index = TreeIndex(db, study_id)
                record_event(
                    db, study_id, "kp_excluded", "ai", kp_id=kp.id,
                    detail={"reason": op.reason, "source": "planning",
                            "progress_before": before, "progress_after": _progress_dict(after_index)},
                    kp_name=kp.name,
                )
                db.commit()
                applied.append("exclude")
            elif op.op == "split":
                kp = db.get(KnowledgePoint, op.node_id or -1)
                if kp is None or kp.study_id != study_id:
                    skip("split", None, "节点不存在")

                    continue
                if edited(kp):
                    skip("split", kp, "用户编辑")

                    continue
                if index.children.get(kp.id):
                    skip("split", kp, "目标已有子节点")

                    continue
                if subtree_has_evidence(db, study_id, index.subtree_ids(kp.id)):
                    skip("split", kp, "学习证据")

                    continue
                chunk_ids = _ordered_chunk_ids(db, kp.id)
                if not chunk_ids:
                    skip("split", kp, "无正文引用")

                    continue
                before = _progress_dict(index)
                db.query(KnowledgeRef).filter(KnowledgeRef.kp_id == kp.id).delete()
                kp.planning_note = op.reason
                for i, part in enumerate(op.parts or [], start=1):
                    child = KnowledgePoint(
                        study_id=study_id, parent_id=kp.id, name=part.title.strip(),
                        sort_order=i, is_chapter=False, origin="ai_split",
                        confidence=0.85, confidence_basis="AI 规划", planning_note=op.reason,
                        chapter_summary=kp.chapter_summary,  # 拆分后子节点继承原摘要
                    )
                    db.add(child)
                    db.flush()
                    si = chunk_ids.index(part.start_chunk_id)
                    ei = chunk_ids.index(part.end_chunk_id)
                    for cid in chunk_ids[si : ei + 1]:
                        db.add(KnowledgeRef(kp_id=child.id, chunk_id=cid, sort_order=cid))
                db.commit()
                _renumber_children(db, kp.id)
                db.commit()
                after_index = TreeIndex(db, study_id)
                record_event(
                    db, study_id, "kp_created", "ai", kp_id=kp.id,
                    detail={"origin": "ai_split", "parent": kp.name, "reason": op.reason,
                            "progress_before": before, "progress_after": _progress_dict(after_index)},
                    kp_name=kp.name,
                )
                db.commit()
                applied.append("split")
            elif op.op == "merge":
                ids = op.node_ids or []
                kps = [db.get(KnowledgePoint, i) for i in ids]
                if any(k is None or k.study_id != study_id for k in kps):
                    skip("merge", None, "节点不存在")
                    continue
                found = [k for k in kps if k is not None]
                a, b = found
                if edited(a) or edited(b):
                    skip("merge", a, "用户编辑")
                    continue
                subtree = index.subtree_ids(a.id) | index.subtree_ids(b.id)
                if subtree_has_evidence(db, study_id, subtree):
                    skip("merge", a, "学习证据")
                    continue
                if index.children.get(a.id) or index.children.get(b.id):
                    skip("merge", a, "目标已有子节点")
                    continue
                before = _progress_dict(index)
                union_ids = sorted(set(_ordered_chunk_ids(db, a.id) + _ordered_chunk_ids(db, b.id)))
                parent_id, sort_pos = a.parent_id, a.sort_order
                # 合并后两份摘要拼接；新节点不是章锚点，摘要留作档案不再被摘要地图读取
                merged_summary = "\n\n".join(
                    s for s in (a.chapter_summary, b.chapter_summary) if s
                )[:CHAPTER_SUMMARY_CHAR_CAP]
                new = KnowledgePoint(
                    study_id=study_id, parent_id=parent_id, name=(op.title or "").strip(),
                    sort_order=sort_pos, is_chapter=False, origin="ai_merge",
                    confidence=0.85, confidence_basis="AI 规划", planning_note=op.reason,
                    chapter_summary=merged_summary or None,
                )
                db.add(new)
                db.flush()
                for cid in union_ids:
                    db.add(KnowledgeRef(kp_id=new.id, chunk_id=cid, sort_order=cid))
                for kp in (a, b):
                    db.query(KnowledgeRef).filter(KnowledgeRef.kp_id == kp.id).delete()
                    db.delete(kp)
                db.commit()
                _renumber_children(db, parent_id)
                db.commit()
                after_index = TreeIndex(db, study_id)
                record_event(
                    db, study_id, "kp_created", "ai", kp_id=new.id,
                    detail={"origin": "ai_merge", "reason": op.reason,
                            "progress_before": before, "progress_after": _progress_dict(after_index)},
                    kp_name=new.name,
                )
                db.commit()
                applied.append("merge")
            elif op.op == "organize":
                ids = op.node_ids or []
                kps = [db.get(KnowledgePoint, i) for i in ids]
                if any(k is None or k.study_id != study_id for k in kps):
                    skip("organize", None, "节点不存在")
                    continue
                targets = [k for k in kps if k is not None]
                if any(edited(k) for k in targets):
                    skip("organize", targets[0], "用户编辑")
                    continue
                before = _progress_dict(index)
                parent_id = targets[0].parent_id
                new = KnowledgePoint(
                    study_id=study_id, parent_id=parent_id, name=(op.title or "").strip(),
                    sort_order=targets[0].sort_order, is_chapter=False, origin="ai_organize",
                    confidence=0.85, confidence_basis="AI 规划", planning_note=op.reason,
                )
                db.add(new)
                db.flush()
                for kp in targets:
                    kp.parent_id = new.id
                db.commit()
                _renumber_children(db, parent_id)
                _renumber_children(db, new.id)
                db.commit()
                after_index = TreeIndex(db, study_id)
                record_event(
                    db, study_id, "kp_created", "ai", kp_id=new.id,
                    detail={"origin": "ai_organize", "reason": op.reason,
                            "progress_before": before, "progress_after": _progress_dict(after_index)},
                    kp_name=new.name,
                )
                db.commit()
                applied.append("organize")
            elif op.op == "group":
                ids = op.chapter_ids or []
                kps = [db.get(KnowledgePoint, i) for i in ids]
                if any(k is None or k.study_id != study_id for k in kps):
                    skip("group", None, "节点不存在")
                    continue
                targets = [k for k in kps if k is not None]
                if any(edited(k) for k in targets):
                    skip("group", targets[0], "用户编辑")
                    continue
                before = _progress_dict(index)
                new = KnowledgePoint(
                    study_id=study_id, parent_id=None, name=(op.title or "").strip(),
                    sort_order=targets[0].sort_order, is_chapter=False, origin="ai_group",
                    confidence=0.85, confidence_basis="AI 规划", planning_note=op.reason,
                )
                db.add(new)
                db.flush()
                for kp in targets:
                    kp.parent_id = new.id
                db.commit()
                _renumber_children(db, None)
                _renumber_children(db, new.id)
                db.commit()
                after_index = TreeIndex(db, study_id)
                record_event(
                    db, study_id, "kp_created", "ai", kp_id=new.id,
                    detail={"origin": "ai_group", "reason": op.reason,
                            "progress_before": before, "progress_after": _progress_dict(after_index)},
                    kp_name=new.name,
                )
                db.commit()
                applied.append("group")
        except Exception:
            db.rollback()
            logger.exception("应用规划操作失败 op=%s", op.op)
            skip(op.op, None, "应用失败（已跳过）")
    return applied, skipped


def _adjust_summary(result: PlanResult, applied: list[str], skipped: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "parts": applied.count("group"),
        "excluded": applied.count("exclude"),
        "split": applied.count("split"),
        "merged": applied.count("merge"),
        "organized": applied.count("organize"),
        "applied": len(applied),
        "skipped": len(skipped),
        "planned": len(result.operations),
    }


def outline_status_dto(db: Session, study: Study) -> dict[str, Any]:
    low_conf = (
        db.query(KnowledgePoint)
        .filter(KnowledgePoint.study_id == study.id, KnowledgePoint.confidence < 0.6)
        .count()
    )
    adjust: dict[str, int] | None = None
    event = (
        db.query(OutlineEvent)
        .filter(OutlineEvent.study_id == study.id, OutlineEvent.event_type == "planning_finished")
        .order_by(OutlineEvent.id.desc())
        .first()
    )
    if event is not None and event.detail_json:
        detail = json.loads(event.detail_json)
        adjust = detail.get("adjust_summary")
    return {
        "status": study.outline_status,
        "error": study.outline_error,
        "thesis": study.outline_thesis,
        "adjust_summary": adjust,
        "low_confidence_count": low_conf,
    }


__all__ = [
    "PlanInvalid",
    "apply_operations",
    "apply_proposal",
    "build_plan_input",
    "decline_proposal",
    "estimate_tokens",
    "generate_proposal",
    "outline_status_dto",
    "planning_stage",
    "proposal_view",
    "start_planning",
    "supersede_pending",
    "validate_plan",
]
