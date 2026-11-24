"""导入管线（技术方案 §4、§9；V0.1.1 技术设计 §1）：三阶段解耦 + 统一预检 + 任务认领 + 启动恢复 + embedding。

阶段 A 结构草稿（零 LLM）→ 阶段 B 正文切片挂引用 → 统一预检（embedding 必检、LLM 勾选才检）
→ embedding 后台启动；AI 规划等用户在消耗确认页点「开始规划」后才跑（outline 服务）。
每个阶段独立事务；引用挂载提交是规划的前置；embedding 后台并行不阻塞。
"""

from __future__ import annotations

import asyncio
import json
import logging
import struct
import threading
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import text, update
from sqlalchemy.orm import Session

from app.core.config import get_config
from app.core.db import get_session_local
from app.core.errors import AppError, Conflict, LLMError, NotFound, Validation
from app.core.llm import embed_texts, load_embed_config
from app.ingest import parse_file
from app.ingest.chunker import chunk_book, location_json
from app.models import KnowledgePoint, KnowledgeRef, OutlineEvent, Source, SourceChunk, Study
from app.services import outline as outline_service
from app.services import precheck
from app.services.events import record_event
from app.services.tree_core import evidence_kp_ids

logger = logging.getLogger(__name__)

LANE_EMBEDDING = "embedding"
LANE_LLM = "llm"
EMBED_RETRYABLE = ("pending", "precheck_failed", "failed", "degraded")


def claim_parse(db: Session, source_id: int) -> bool:
    from typing import Any, cast

    from sqlalchemy.engine import CursorResult

    r = cast(
        CursorResult[Any],
        db.execute(
            update(Source)
            .where(Source.id == source_id, Source.parse_status == "pending")
            .values(parse_status="parsing", parse_error=None)
        ),
    )
    return bool(r.rowcount)


def claim_embed(db: Session, source_id: int) -> bool:
    from typing import Any, cast

    from sqlalchemy.engine import CursorResult

    r = cast(
        CursorResult[Any],
        db.execute(
            update(Source)
            .where(
                Source.id == source_id,
                Source.embed_status.in_(("pending", "failed", "degraded")),
            )
            .values(embed_status="running", embed_error=None)
        ),
    )
    return bool(r.rowcount)


def _fail_parse(db: Session, source_id: int, message: str) -> None:
    db.execute(
        update(Source).where(Source.id == source_id).values(
            parse_status="failed", parse_error=message
        )
    )
    db.commit()


def run_parse(source_id: int, *, start_precheck: bool = True) -> None:
    """后台解析任务（sync，线程池运行）；解析后起预检线程（测试可关）。"""
    db = get_session_local()()
    try:
        source = db.get(Source, source_id)
        if source is None:
            return
        if not claim_parse(db, source_id):
            return
        db.commit()
        try:
            book = parse_file(Path(source.stored_path), source.type)
        except AppError as e:
            _fail_parse(db, source_id, e.detail)
            return
        except Exception as e:
            logger.exception("解析内部错误 source=%s", source_id)
            _fail_parse(db, source_id, f"解析时发生内部错误（{e.__class__.__name__}）")
            return

        study = db.get(Study, source.study_id)
        assert study is not None
        try:
            event_id = _stage_a_structure(db, study, source, book)
            _stage_b_chunks(db, study, source, book, event_id)
        except Exception as e:
            db.rollback()
            logger.exception("建树/挂引用失败 source=%s", source_id)
            _fail_parse(db, source_id, f"建立结构时发生内部错误（{e.__class__.__name__}）")
            return

        if start_precheck:
            # 解析后统一预检（B6-02）；embedding 与 AI 规划都在预检之后才各自继续
            _start_precheck(study.id)
    finally:
        db.close()


def _start_precheck(study_id: int) -> None:
    threading.Thread(
        target=_precheck_worker, args=(study_id,), daemon=True, name=f"precheck-{study_id}"
    ).start()


def _start_embed(source_id: int) -> None:
    threading.Thread(
        target=_embed_worker, args=(source_id,), daemon=True, name=f"embed-{source_id}"
    ).start()


def launch_planning(study_id: int) -> None:
    threading.Thread(
        target=_plan_worker, args=(study_id,), daemon=True, name=f"plan-{study_id}"
    ).start()


def _precheck_worker(study_id: int) -> None:
    try:
        asyncio.run(precheck_and_dispatch(study_id))
    except Exception:
        logger.exception("预检任务异常 study=%s", study_id)


def _embed_worker(source_id: int) -> None:
    try:
        asyncio.run(embed_source(source_id))
    except Exception:
        logger.exception("embedding 任务异常 source=%s", source_id)


def _plan_worker(study_id: int) -> None:
    try:
        asyncio.run(outline_service.generate_proposal(study_id))
    except Exception:
        logger.exception("AI 规划任务异常 study=%s", study_id)


def _stage_a_structure(
    db: Session, study: Study, source: Source, book: object
) -> int | None:
    """阶段 A：结构草稿（零 LLM），独立事务；返回 structure_built 事件 id。"""
    from app.ingest.types import ParsedBook

    assert isinstance(book, ParsedBook)
    kp_by_key: dict[str, KnowledgePoint] = {}
    for node in book.tree_nodes:
        kp = KnowledgePoint(
            study_id=study.id,
            parent_id=None,  # flush 后按 key 回填，避免读到未生成的 id
            name=node.title,
            sort_order=node.order,
            is_chapter=node.is_chapter,
            origin="toc" if book.confidence_basis == "原书目录" else "heading",
            confidence=book.confidence,
            confidence_basis=book.confidence_basis,
        )
        db.add(kp)
        kp_by_key[node.key] = kp
    db.flush()
    for node in book.tree_nodes:
        if node.parent_key:
            kp_by_key[node.key].parent_id = kp_by_key[node.parent_key].id
    db.flush()
    event_id: int | None = None
    if book.tree_nodes:
        snapshot = {
            "nodes": [
                {
                    "id": kp_by_key[node.key].id,
                    "name": kp_by_key[node.key].name,
                    "parent_id": kp_by_key[node.key].parent_id,
                    "sort_order": kp_by_key[node.key].sort_order,
                    "is_chapter": kp_by_key[node.key].is_chapter,
                    "origin": kp_by_key[node.key].origin,
                    "confidence": kp_by_key[node.key].confidence,
                    "confidence_basis": kp_by_key[node.key].confidence_basis,
                    "excluded": False,
                }
                for node in book.tree_nodes
            ],
            "refs": {},
        }
        event = record_event(
            db,
            study.id,
            "structure_built",
            "structure",
            detail=snapshot,
        )
        db.flush()
        event_id = event.id
        study.outline_status = "structure_ready"
    db.commit()
    return event_id


def _stage_b_chunks(
    db: Session, study: Study, source: Source, book: object, event_id: int | None
) -> None:
    """阶段 B：切片 + 引用挂载（独立事务）；引用提交后回填快照 refs。"""
    from app.ingest.types import ParsedBook

    assert isinstance(book, ParsedBook)
    kp_by_key: dict[str, KnowledgePoint] = {}
    if book.tree_nodes:
        kps = (
            db.query(KnowledgePoint)
            .filter(KnowledgePoint.study_id == study.id)
            .order_by(KnowledgePoint.sort_order)
            .all()
        )
        kp_by_key = {str(k.sort_order): k for k in kps}  # sort_order 即建树序号（stage A）

    drafts = chunk_book(book)
    refs_by_kp: dict[int, list[int]] = {}
    for order, draft in enumerate(drafts, start=1):
        chunk = SourceChunk(
            source_id=source.id,
            sort_order=order,
            level_path=draft.level_path,
            title=draft.title,
            content=draft.content,
            location=location_json(draft.location),
            char_count=len(draft.content),
        )
        db.add(chunk)
        db.flush()
        if draft.node_key is not None and draft.node_key in kp_by_key:
            kp = kp_by_key[draft.node_key]
            db.add(
                KnowledgeRef(kp_id=kp.id, chunk_id=chunk.id, sort_order=order)
            )
            refs_by_kp.setdefault(kp.id, []).append(chunk.id)
    source.parse_status = "parsed"
    source.parse_error = None
    db.commit()

    if event_id is not None and refs_by_kp:
        event = db.get(OutlineEvent, event_id)
        if event is not None and event.detail_json:
            detail = json.loads(event.detail_json)
            detail["refs"] = {str(k): v for k, v in refs_by_kp.items()}
            event.detail_json = json.dumps(detail, ensure_ascii=False)
            db.commit()


def _purge_structure(db: Session, study_id: int, source_id: int) -> None:
    """重解析前清空旧结构数据（调用方已保证无学习证据）。"""
    db.execute(
        text(
            "DELETE FROM vec_chunks WHERE chunk_id IN"
            " (SELECT id FROM source_chunks WHERE source_id = :src)"
        ),
        {"src": source_id},
    )
    db.execute(
        text(
            "DELETE FROM knowledge_refs WHERE chunk_id IN"
            " (SELECT id FROM source_chunks WHERE source_id = :src)"
        ),
        {"src": source_id},
    )
    db.execute(text("DELETE FROM knowledge_points WHERE study_id = :sid"), {"sid": study_id})
    db.execute(text("DELETE FROM source_chunks WHERE source_id = :src"), {"src": source_id})
    db.commit()


def reparse(db: Session, source_id: int) -> Source:
    """重试解析（决策 #29）：仅解析失败重试与无目录重识别；暂存成功后原子替换。
    只做 gate 与状态重置；实际解析由调用方作为后台任务调度 run_parse。"""
    source = db.get(Source, source_id)
    if source is None:
        from app.core.errors import NotFound

        raise NotFound("资料不存在")
    study = db.get(Study, source.study_id)
    assert study is not None

    from app.services.tree_core import evidence_kp_ids

    has_structure = (
        db.query(KnowledgePoint.id).filter(KnowledgePoint.study_id == study.id).first()
        is not None
    )
    if source.parse_status == "parsed" and has_structure:
        raise Conflict("该书已有可用结构，无需重新识别")
    if evidence_kp_ids(db, study.id):
        raise Conflict("该书已有学习记录（会话/测验/笔记/点亮），不能重解析；可逐个排除不学的内容")
    if source.parse_status == "parsing":
        raise Conflict("解析正在进行中")

    _purge_structure(db, study.id, source.id)
    outline_service.supersede_pending(db, study.id)
    db.execute(
        update(Source)
        .where(Source.id == source.id)
        .values(parse_status="pending", parse_error=None, embed_status="pending", embed_error=None)
    )
    db.execute(
        update(Study).where(Study.id == study.id).values(
            outline_status="idle", outline_error=None, outline_thesis=None
        )
    )
    db.commit()
    return source


async def reembed(db: Session, source_id: int) -> dict[str, object]:
    """embedding 重试（B6-06 验收 1）：先重新预检，通过才启动。"""
    source = db.get(Source, source_id)
    if source is None:
        raise NotFound("资料不存在")
    if source.embed_status not in ("precheck_failed", "failed", "degraded"):
        raise Conflict("仅预检失败、失败或降级状态的资料可以重试")
    result = await precheck_and_dispatch(source.study_id, lanes=(LANE_EMBEDDING,))
    embedding = result[LANE_EMBEDDING]
    return {
        "status": "reembed_started" if embedding["ok"] else "precheck_failed",
        "embedding": embedding,
    }


def _gate_replanning(db: Session, study: Study) -> None:
    """再规划的前置：进行中/待确认不让路；已应用且有学习证据的书不能重新规划（B6-06 验收 3）。"""
    status = study.outline_status
    if status == "planning":
        raise Conflict("AI 规划正在进行中，请稍候")
    if status == "awaiting_confirm":
        raise Conflict("已有待确认的规划建议，请先确认或拒绝")
    has_structure = (
        db.query(KnowledgePoint.id).filter(KnowledgePoint.study_id == study.id).first() is not None
    )
    if not has_structure:
        raise Validation("这本书没有可用的结构，无法进行 AI 规划")
    if status == "ready" and evidence_kp_ids(db, study.id):
        raise Conflict("这本书已有学习记录，不能重新规划；可在目录树中手动编辑")


async def precheck_study(
    db: Session, study_id: int, *, lanes: Sequence[str] | None = None
) -> dict[str, dict[str, object]]:
    """POST /studies/{id}/precheck（B6-06 手动重试入口）；lanes 缺省两路。"""
    study = db.get(Study, study_id)
    if study is None:
        raise NotFound("学习项目不存在")
    if lanes is None:
        lanes = (LANE_EMBEDDING, LANE_LLM)
    if LANE_LLM in lanes:
        _gate_replanning(db, study)
        study.use_ai_planning = True  # 未勾选后改主意：从星图页补启动（B6-06 验收 2）
        db.commit()
    return await precheck_and_dispatch(study_id, lanes=tuple(lanes))


async def precheck_and_dispatch(
    study_id: int, *, lanes: Sequence[str] | None = None
) -> dict[str, dict[str, object]]:
    """统一预检（B6-02）：探测 → 落状态 → embedding 通即后台启动。

    lanes 缺省按书的勾选状态决定检不检 LLM；预检不通只落状态，不重试。
    """
    db = get_session_local()()
    try:
        study = db.get(Study, study_id)
        if study is None:
            raise NotFound("学习项目不存在")
        if lanes is None:
            checked = study.use_ai_planning and study.outline_status == "structure_ready"
            lanes = (LANE_EMBEDDING, LANE_LLM) if checked else (LANE_EMBEDDING,)
        source = db.get(Source, study.primary_source_id) if study.primary_source_id else None
        results: dict[str, precheck.LaneResult] = {}
        if LANE_EMBEDDING in lanes and source is not None:
            results[LANE_EMBEDDING] = await precheck.probe_embedding(db)
        if LANE_LLM in lanes:
            results[LANE_LLM] = await precheck.probe_llm(db)

        # 探测期间（最长 15 秒）用户可能已推进状态：写回前重读，只改仍停在可启动状态的路
        db.expire_all()
        embedding = results.get(LANE_EMBEDDING)
        if source is not None and embedding is not None:
            db.refresh(source)
            if source.embed_status in EMBED_RETRYABLE:
                source.embed_status = "pending" if embedding.ok else "precheck_failed"
                source.embed_error = None if embedding.ok else embedding.detail
        llm = results.get(LANE_LLM)
        if llm is not None:
            db.refresh(study)
            if study.outline_status in outline_service.PLAN_RETRYABLE:
                study.outline_status = "precheck_ok" if llm.ok else "precheck_failed"
                study.outline_error = None if llm.ok else llm.detail
        db.commit()
        if source is not None and embedding is not None and embedding.ok:
            _start_embed(source.id)
        return {lane: r.as_dict() for lane, r in results.items()}
    finally:
        db.close()


async def embed_source(source_id: int) -> None:
    """embedding 后台任务：pending→running；ready/degraded/failed；不阻塞核心链路。"""
    db = get_session_local()()
    try:
        source = db.get(Source, source_id)
        if source is None:
            return
        if not claim_embed(db, source_id):
            return
        db.commit()
        if not get_config().llm_stub:  # 桩 embedding 不需要真实配置
            try:
                load_embed_config(db)
            except LLMError as e:
                db.execute(
                    update(Source)
                    .where(Source.id == source_id)
                    .values(embed_status="precheck_failed", embed_error=str(e.detail))
                )
                db.commit()
                return

        chunks = (
            db.query(SourceChunk)
            .filter(SourceChunk.source_id == source_id)
            .order_by(SourceChunk.sort_order)
            .all()
        )
        if not chunks:
            db.execute(
                update(Source).where(Source.id == source_id).values(embed_status="ready")
            )
            db.commit()
            return

        db.execute(
            text(
                "DELETE FROM vec_chunks WHERE chunk_id IN"
                " (SELECT id FROM source_chunks WHERE source_id = :src)"
            ),
            {"src": source_id},
        )
        db.commit()

        failed = 0
        done = 0
        batch = 16
        for i in range(0, len(chunks), batch):
            group = chunks[i : i + batch]
            ok = False
            for _ in range(2):  # 每批一次重试
                try:
                    vectors = await embed_texts(db, [c.content for c in group])
                    for chunk, vec in zip(group, vectors, strict=True):
                        blob = b"".join(struct.pack("<f", x) for x in vec)
                        db.execute(
                            text(
                                "INSERT INTO vec_chunks(chunk_id, embedding) VALUES (:c, :e)"
                            ),
                            {"c": chunk.id, "e": blob},
                        )
                    db.commit()
                    done += len(group)
                    ok = True
                    break
                except LLMError:
                    db.rollback()
                    continue
            if not ok:
                failed += len(group)

        if failed == 0:
            status, err = "ready", None
        elif done > 0:
            status, err = "degraded", f"{failed} 个切片向量化失败（可重试）"
        else:
            status, err = "failed", "embedding 全部失败（可重试）"
        db.execute(
            update(Source)
            .where(Source.id == source_id)
            .values(embed_status=status, embed_error=err)
        )
        db.commit()
    finally:
        db.close()


def recover_on_startup() -> None:
    """启动恢复（P1-02、B1-03）：中断态转可重试失败；pending 任务重新入队。"""
    db = get_session_local()()
    try:
        db.execute(
            update(Source)
            .where(Source.parse_status == "parsing")
            .values(parse_status="failed", parse_error="进程中断，可重试")
        )
        db.execute(
            update(Source)
            .where(Source.embed_status == "running")
            .values(embed_status="failed", embed_error="进程中断，可重试")
        )
        db.execute(
            update(Study)
            .where(Study.outline_status == "planning")
            .values(outline_status="failed", outline_error="进程中断，可重试")
        )
        db.commit()

        pending_sources = (
            db.query(Source.id).filter(Source.parse_status == "pending").all()
        )
        for (sid,) in pending_sources:
            threading.Thread(
                target=run_parse, args=(sid,), daemon=True
            ).start()

        # 预检没来得及生效（解析后、或预检通过与线程启动之间中断）：重做一次；
        # precheck_failed 不在此列——预检失败只能由用户手动重试（B6-02 验收 4）
        unchecked = db.execute(
            text(
                "SELECT s.id FROM studies s JOIN sources src ON src.id = s.primary_source_id"
                " WHERE src.parse_status = 'parsed' AND src.embed_status = 'pending'"
            )
        ).scalars().all()
        for sid in unchecked:
            _start_precheck(sid)

        # 清理孤儿临时文件
        uploads = get_config().uploads_dir
        for p in uploads.glob("tmp_*.part"):
            try:
                p.unlink()
            except OSError:
                logger.warning("清理孤儿临时文件失败：%s", p)
    finally:
        db.close()


def pipeline_progress(db: Session, study_id: int) -> dict[str, object]:
    """GET /studies/{id}/progress 数据源（接口设计 §2）。"""
    study = db.get(Study, study_id)
    if study is None:
        raise Validation("学习项目不存在")
    source = db.get(Source, study.primary_source_id) if study.primary_source_id else None
    parse = {"status": source.parse_status if source else "pending",
             "error": source.parse_error if source else None}
    embed_total = 0
    embed_done = 0
    if source is not None:
        embed_total = (
            db.query(SourceChunk.id).filter(SourceChunk.source_id == source.id).count()
        )
        embed_done = int(
            db.execute(
                text(
                    "SELECT COUNT(*) FROM vec_chunks WHERE chunk_id IN"
                    " (SELECT id FROM source_chunks WHERE source_id = :src)"
                ),
                {"src": source.id},
            ).scalar()
            or 0
        )
    embedding = {
        "status": source.embed_status if source else "pending",
        "done": embed_done,
        "total": embed_total,
        "error": source.embed_error if source else None,
    }
    outline = {
        "status": study.outline_status,
        "error": study.outline_error,
        "thesis": study.outline_thesis,
        "stage": outline_service.planning_stage(study_id),
        "ai_planning": study.use_ai_planning,
    }
    return {"parse": parse, "outline": outline, "embedding": embedding}


async def search_similar(
    db: Session, source_id: int, query: str, *, k: int, exclude_ids: set[int]
) -> list[int]:
    """本书向量检索补足（技术方案 §8 第 3 层）；失败返回空，不阻塞。"""
    try:
        vectors = await embed_texts(db, [query])
    except LLMError:
        return []
    blob = b"".join(struct.pack("<f", x) for x in vectors[0])
    rows = db.execute(
        text(
            "SELECT v.chunk_id, s.source_id FROM vec_chunks v"
            " JOIN source_chunks s ON s.id = v.chunk_id"
            " WHERE v.embedding MATCH :e AND k = :k ORDER BY distance"
        ),
        {"e": blob, "k": max(k + len(exclude_ids), k * 2)},
    ).all()
    out = [cid for cid, sid in rows if sid == source_id and cid not in exclude_ids]
    return out[:k]


__all__ = [
    "embed_source",
    "launch_planning",
    "pipeline_progress",
    "precheck_and_dispatch",
    "precheck_study",
    "recover_on_startup",
    "reembed",
    "reparse",
    "run_parse",
    "search_similar",
]
