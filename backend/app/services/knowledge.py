"""知识点模块(M2-01/02/03):拆解落库(含依赖)、树查询、编辑操作。"""

from collections.abc import Callable, Sequence

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.agents import decompose
from app.models import (
    Card,
    KnowledgePoint,
    KnowledgeRef,
    KpDependency,
    LearningSession,
    MasteryEvent,
    Quiz,
    SourceChunk,
    StudySource,
    Task,
)


def decompose_source(
    db: Session,
    study_id: int,
    source_id: int,
    on_batch: Callable[[int, int], None] | None = None,
) -> int:
    """对该 study 拆解该 source 并落库(旧结果已在切片替换前清理),返回写入节点数。"""
    chunks = db.scalars(
        select(SourceChunk)
        .where(SourceChunk.source_id == source_id)
        .order_by(SourceChunk.seq)
    ).fetchall()
    if not chunks:
        return 0

    result = decompose.run_pipeline(
        [
            {
                "chunk_id": c.id,
                "heading_path": c.heading_path,
                "content": c.content,
            }
            for c in chunks
        ],
        on_batch=on_batch,
    )
    if not result["tree"] and result.get("errors"):
        # 批次错误在 extract_node 已收集;全空说明拆解没产出,必须外露而非静默成功(M2-01)
        raise RuntimeError(f"拆解批次失败,未产出知识点;首条错误: {result['errors'][0]}")
    count = _insert_tree(db, study_id, result["tree"])

    # 依赖落库:name → id 映射(树内唯一),成环边丢弃
    if result.get("dependencies"):
        name_to_id = dict(
            db.execute(
                select(KnowledgePoint.name, KnowledgePoint.id).where(
                    KnowledgePoint.study_id == study_id
                )
            ).all()
        )
        existing = set(
            db.execute(
                select(KpDependency.kp_id, KpDependency.depends_on_kp_id).where(
                    KpDependency.kp_id.in_(name_to_id.values())
                )
            ).all()
        )
        edges: set[tuple[int, int]] = {
            (name_to_id[e["kp"]], name_to_id[e["depends_on"]])
            for e in result["dependencies"]
            if e["kp"] in name_to_id and e["depends_on"] in name_to_id
        }
        # 邻接表只含已提交的边;候选边边加边入表(同批互检也能发现反向成环)
        adjacency: dict[int, list[int]] = {}
        for kp_id, dep_id in existing:
            adjacency.setdefault(dep_id, []).append(kp_id)

        def reaches(start: int, goal: int, seen: set[int]) -> bool:
            if start == goal:
                return True
            return any(
                reaches(nxt, goal, seen | {nxt})
                for nxt in adjacency.get(start, [])
                if nxt not in seen
            )

        for kp_id, dep_id in sorted(edges - existing):
            # kp 依赖 dep;若 dep 已(间接)依赖 kp,加这条边会成环,丢弃
            if not reaches(dep_id, kp_id, {dep_id}):
                db.add(KpDependency(kp_id=kp_id, depends_on_kp_id=dep_id))
                adjacency.setdefault(dep_id, []).append(kp_id)
    return count


def delete_source_kps(db: Session, study_ids: Sequence[int], source_id: int) -> None:
    """删除"全部引用都落在本资料"的知识点;无引用的(AI 推断/用户手建)保留。

    必须在删除切片之前调用:切片删除会级联清引用,之后无法凭引用识别旧知识点。
    shortcut: 用户编辑(M2-03,M3 上线)后需改为增量合并;当前重新拆解即整树再生,自用可接受
    """
    source_chunk_ids = set(
        db.scalars(select(SourceChunk.id).where(SourceChunk.source_id == source_id))
    )
    if not source_chunk_ids:
        return
    for study_id in study_ids:
        kps = db.scalars(
            select(KnowledgePoint).where(KnowledgePoint.study_id == study_id)
        ).fetchall()
        for kp in kps:
            refs = set(
                db.scalars(select(KnowledgeRef.chunk_id).where(KnowledgeRef.kp_id == kp.id))
            )
            if refs and refs <= source_chunk_ids:
                db.execute(delete(KnowledgeRef).where(KnowledgeRef.kp_id == kp.id))
                # 子节点提为根,避免整树因父删除丢失
                for child in db.scalars(
                    select(KnowledgePoint).where(KnowledgePoint.parent_id == kp.id)
                ).fetchall():
                    child.parent_id = kp.parent_id
                db.delete(kp)


def _insert_tree(db: Session, study_id: int, tree: list[dict], parent_id: int | None = None) -> int:
    count = 0
    for order, node in enumerate(tree):
        kp = KnowledgePoint(
            study_id=study_id,
            parent_id=parent_id,
            name=node["name"][:300],
            summary=node.get("summary", ""),
            kp_type=node.get("kp_type", "concept"),
            ai_inferred=node.get("ai_inferred", False),
            sort_order=order,
        )
        db.add(kp)
        db.flush()
        for chunk_id in node.get("refs", []):
            db.add(KnowledgeRef(kp_id=kp.id, chunk_id=chunk_id))
        count += 1 + _insert_tree(db, study_id, node.get("children", []), kp.id)
    return count


def get_tree(db: Session, study_id: int) -> list[dict]:
    """嵌套树,refs 带 chunk 定位信息供前端跳转阅读页。"""
    kps = db.scalars(
        select(KnowledgePoint)
        .where(KnowledgePoint.study_id == study_id)
        .order_by(KnowledgePoint.sort_order, KnowledgePoint.id)
    ).fetchall()
    chunk_map = {
        c.id: c
        for c in db.scalars(
            select(SourceChunk).where(
                SourceChunk.id.in_(
                    select(KnowledgeRef.chunk_id).where(
                        KnowledgeRef.kp_id.in_([kp.id for kp in kps])
                    )
                )
            )
        )
    }

    def node_of(kp: KnowledgePoint) -> dict:
        refs = db.scalars(
            select(KnowledgeRef.chunk_id).where(KnowledgeRef.kp_id == kp.id)
        ).fetchall()
        return {
            "id": kp.id,
            "name": kp.name,
            "summary": kp.summary,
            "kp_type": kp.kp_type,
            "ai_inferred": kp.ai_inferred,
            "mastery_status": kp.mastery_status,
            "self_reported": kp.self_reported,
            "refs": [
                {
                    "chunk_id": cid,
                    "source_id": chunk_map[cid].source_id,
                    "heading_path": chunk_map[cid].heading_path,
                }
                for cid in refs
                if cid in chunk_map
            ],
            "children": [],
        }

    nodes = {kp.id: node_of(kp) for kp in kps}
    roots: list[dict] = []
    for kp in kps:
        if kp.parent_id and kp.parent_id in nodes:
            nodes[kp.parent_id]["children"].append(nodes[kp.id])
        else:
            roots.append(nodes[kp.id])
    return roots


def study_source_ids(db: Session, study_id: int) -> Sequence[int]:
    return db.scalars(
        select(StudySource.source_id).where(StudySource.study_id == study_id)
    ).fetchall()


def has_ready_sources(db: Session, study_id: int) -> bool:
    """是否存在已解析就绪的资料(决定能否只重跑拆解而不必重新解析)。"""
    return (
        db.scalar(
            select(SourceChunk.source_id)
            .where(SourceChunk.source_id.in_(study_source_ids(db, study_id)))
            .limit(1)
        )
        is not None
    )


# ---------- 编辑(M2-03):改名/删除/新增/合并;计划与档案经外键与 join 同步生效 ----------


def update_kp(
    db: Session, kp: KnowledgePoint, *, name: str | None, summary: str | None
) -> KnowledgePoint:
    if name is not None:
        kp.name = name[:300]
    if summary is not None:
        kp.summary = summary
    db.commit()
    db.refresh(kp)
    return kp


def create_kp(
    db: Session, study_id: int, *, name: str, summary: str = "", parent_id: int | None = None
) -> KnowledgePoint:
    siblings = db.scalar(
        select(KnowledgePoint.id)
        .where(KnowledgePoint.study_id == study_id, KnowledgePoint.parent_id == parent_id)
        .order_by(KnowledgePoint.sort_order.desc())
        .limit(1)
    )
    kp = KnowledgePoint(
        study_id=study_id,
        parent_id=parent_id,
        name=name[:300],
        summary=summary,
        sort_order=(siblings + 1) if siblings is not None else 0,
    )
    db.add(kp)
    db.commit()
    db.refresh(kp)
    return kp


def delete_kp(db: Session, kp: KnowledgePoint) -> None:
    """删除知识点:任务/卡片/测验随删(FK CASCADE);子节点提为根。"""
    for child in db.scalars(
        select(KnowledgePoint).where(KnowledgePoint.parent_id == kp.id)
    ).fetchall():
        child.parent_id = kp.parent_id
    db.delete(kp)  # refs/deps/tasks/cards/quizzes 由 CASCADE 处理
    db.commit()


def merge_kps(db: Session, source: KnowledgePoint, target: KnowledgePoint) -> KnowledgePoint:
    """把 source 合并进 target:refs/子节点/关联数据/依赖边全部转移后删除 source。"""
    if source.id == target.id or source.study_id != target.study_id:
        raise ValueError("合并目标无效")

    # target 不能是 source 的后代(否则树成环)
    node: int | None = target.id
    while node is not None:
        if node == source.id:
            raise ValueError("不能合并到自己的后代节点")
        parent = db.get(KnowledgePoint, node)
        node = parent.parent_id if parent else None

    target_refs = set(
        db.scalars(select(KnowledgeRef.chunk_id).where(KnowledgeRef.kp_id == target.id))
    )
    for ref in db.scalars(
        select(KnowledgeRef).where(KnowledgeRef.kp_id == source.id)
    ).fetchall():
        if ref.chunk_id not in target_refs:
            db.execute(
                update(KnowledgeRef)
                .where(KnowledgeRef.kp_id == source.id, KnowledgeRef.chunk_id == ref.chunk_id)
                .values(kp_id=target.id)
            )
    db.execute(delete(KnowledgeRef).where(KnowledgeRef.kp_id == source.id))

    for child in db.scalars(
        select(KnowledgePoint).where(KnowledgePoint.parent_id == source.id)
    ).fetchall():
        child.parent_id = target.id

    for model in (Card, Quiz, Task, MasteryEvent, LearningSession):
        db.execute(
            update(model).where(model.kp_id == source.id).values(kp_id=target.id)
        )
    # 依赖边转移(去重后)
    target_edges = set(
        db.execute(
            select(KpDependency.kp_id, KpDependency.depends_on_kp_id).where(
                KpDependency.kp_id == target.id
            )
        ).all()
    )
    for edge in db.execute(
        select(KpDependency.kp_id, KpDependency.depends_on_kp_id).where(
            KpDependency.kp_id == source.id
        )
    ).all():
        if edge not in target_edges:
            db.execute(
                update(KpDependency)
                .where(
                    KpDependency.kp_id == source.id,
                    KpDependency.depends_on_kp_id == edge[1],
                )
                .values(kp_id=target.id)
            )
    db.execute(delete(KpDependency).where(KpDependency.kp_id == source.id))
    db.execute(delete(KpDependency).where(KpDependency.depends_on_kp_id == source.id))

    if not target.summary and source.summary:
        target.summary = source.summary
    db.delete(source)
    db.commit()
    db.refresh(target)
    return target


def get_graph(db: Session, study_id: int) -> dict:
    """依赖图数据(M2-02,@xyflow 用)。"""
    kps = db.scalars(
        select(KnowledgePoint).where(KnowledgePoint.study_id == study_id)
    ).fetchall()
    ids = [kp.id for kp in kps]
    edges = (
        db.execute(
            select(KpDependency.kp_id, KpDependency.depends_on_kp_id).where(
                KpDependency.kp_id.in_(ids)
            )
        ).all()
        if ids
        else []
    )
    return {
        "nodes": [
            {
                "id": kp.id,
                "name": kp.name,
                "kp_type": kp.kp_type,
                "mastery_status": kp.mastery_status,
                "ai_inferred": kp.ai_inferred,
            }
            for kp in kps
        ],
        "edges": [
            {"source": kp_id, "depends_on": dep_id} for kp_id, dep_id in edges
        ],
    }


def load_leaves_with_deps(
    db: Session, study_id: int
) -> tuple[list[KnowledgePoint], list[tuple[int, int]]]:
    """计划排程输入:叶子知识点 + 依赖边(仅保留两端都是叶子的边)。

    自评"已掌握"的叶子不进计划(M2-07);快速验证不通过会回滚 self_reported 后重新生成。
    """
    kps = db.scalars(
        select(KnowledgePoint)
        .where(KnowledgePoint.study_id == study_id)
        .order_by(KnowledgePoint.sort_order, KnowledgePoint.id)
    ).fetchall()
    parent_ids = {kp.parent_id for kp in kps if kp.parent_id is not None}
    leaves = [
        kp for kp in kps if kp.id not in parent_ids and kp.self_reported != "mastered"
    ]
    leaf_ids = {kp.id for kp in leaves}
    edges = [
        (kp_id, dep_id)
        for kp_id, dep_id in db.execute(
            select(KpDependency.kp_id, KpDependency.depends_on_kp_id).where(
                KpDependency.kp_id.in_(leaf_ids),
                KpDependency.depends_on_kp_id.in_(leaf_ids),
            )
        ).all()
    ]
    return leaves, edges


# ---------- 自评跳过(M2-07, 与 M6-03 自评分离共用字段) ----------


def set_self_reported(db: Session, kp: KnowledgePoint, mastered: bool) -> KnowledgePoint:
    kp.self_reported = "mastered" if mastered else "unknown"
    db.commit()
    db.refresh(kp)
    return kp


def quick_quiz(db: Session, kp: KnowledgePoint) -> Quiz:
    """快速验证(M2-07):出 1 道客观题验证自评;不通过则回滚进计划。"""
    import uuid

    from app.services import quiz as quiz_svc

    session = LearningSession(
        study_id=kp.study_id, kp_id=kp.id, session_type="free", thread_id=uuid.uuid4().hex
    )
    db.add(session)
    db.flush()
    rows = quiz_svc.generate_for_session(db, session)
    keep = next((q for q in rows if q.q_type == "objective"), rows[0])
    for q in rows:
        if q.id != keep.id:
            db.delete(q)
    db.commit()
    db.refresh(keep)
    return keep


def rollback_self_report(db: Session, kp: KnowledgePoint) -> None:
    """快速验证不通过:回滚自评并补进当前 active 计划(明天)。"""
    from datetime import timedelta

    from app.config import today
    from app.models import Plan

    kp.self_reported = "unknown"
    plan = db.scalar(
        select(Plan).where(Plan.study_id == kp.study_id, Plan.status == "active")
    )
    if plan is not None and not db.scalar(
        select(Task.id).where(
            Task.plan_id == plan.id,
            Task.kp_id == kp.id,
            Task.task_type == "learn",
            Task.status == "pending",
        )
    ):
        db.add(
            Task(
                plan_id=plan.id,
                study_id=kp.study_id,
                kp_id=kp.id,
                task_type="learn",
                scheduled_date=today() + timedelta(days=1),
                estimated_minutes=25,
            )
        )
    db.commit()
