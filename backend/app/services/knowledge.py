"""知识点模块(M2-01):拆解落库、树查询。"""

from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.agents import decompose
from app.models import KnowledgePoint, KnowledgeRef, SourceChunk, StudySource


def decompose_source(db: Session, study_id: int, source_id: int) -> int:
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
        ]
    )
    return _insert_tree(db, study_id, result["tree"])


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
