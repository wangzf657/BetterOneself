"""骨架派生口径（决策 #27、数据模型 §4）——全站唯一分母与三态来源。

有效学习单元 = 结构叶（无子节点，与子节点是否排除无关）
             ∧ 自身及全部祖先未排除 ∧ knowledge_refs ≥ 1。
容器节点（父节点、部分层、有子节点的章）不进分母、无三态、无学习入口。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import KnowledgePoint, KnowledgeRef, Message, Note, Quiz, Session_


@dataclass(frozen=True)
class Progress:
    lighted: int
    total: int
    percent: float | None  # 分母为 0 → None（前端显示「—（无有效学习单元）」）

    def as_dict(self) -> dict[str, float | int | None]:
        return {
            "lighted": self.lighted,
            "total": self.total,
            "percent": round(self.percent, 1) if self.percent is not None else None,
        }


class TreeIndex:
    """一次加载整树，派生所有口径；excluded_extra/excluded_removed 供预览与前后值计算。"""

    def __init__(
        self,
        db: Session,
        study_id: int,
        *,
        excluded_extra: set[int] | None = None,
        excluded_removed: set[int] | None = None,
    ) -> None:
        self.db = db
        self.study_id = study_id
        self.kps: list[KnowledgePoint] = (
            db.query(KnowledgePoint)
            .filter(KnowledgePoint.study_id == study_id)
            .order_by(KnowledgePoint.sort_order, KnowledgePoint.id)
            .all()
        )
        self.by_id: dict[int, KnowledgePoint] = {k.id: k for k in self.kps}
        self.children: dict[int | None, list[KnowledgePoint]] = {}
        for kp in self.kps:
            self.children.setdefault(kp.parent_id, []).append(kp)

        ref_rows = db.execute(
            select(KnowledgeRef.kp_id, func.count())
            .join(KnowledgePoint, KnowledgePoint.id == KnowledgeRef.kp_id)
            .where(KnowledgePoint.study_id == study_id)
            .group_by(KnowledgeRef.kp_id)
        ).all()
        self.refs_count: dict[int, int] = {kp_id: c for kp_id, c in ref_rows}

        # 有效排除标记：自身或任一祖先 excluded（叠加预览的额外排除/移除恢复）
        self._excluded: set[int] = set()
        for kp in self.kps:
            if self._self_or_ancestor_excluded(kp, excluded_extra, excluded_removed):
                self._excluded.add(kp.id)

        # 学习中：存在任一 message 或 quiz 记录（quiz 也是学习活动）
        msg_kps = db.execute(
            select(Session_.kp_id).join(Message, Message.session_id == Session_.id).distinct()
        ).scalars().all()
        quiz_kps = db.execute(select(Quiz.kp_id).distinct()).scalars().all()
        self.learning_kps: set[int] = set(msg_kps) | set(quiz_kps)

        # 有效学习单元
        self.valid_units: set[int] = set()
        for kp in self.kps:
            if (
                not self.children.get(kp.id)
                and kp.id not in self._excluded
                and self.refs_count.get(kp.id, 0) >= 1
            ):
                self.valid_units.add(kp.id)

    def _self_or_ancestor_excluded(
        self,
        kp: KnowledgePoint,
        extra: set[int] | None,
        removed: set[int] | None,
    ) -> bool:
        cur: KnowledgePoint | None = kp
        while cur is not None:
            if removed and cur.id in removed:
                cur = self.by_id.get(cur.parent_id) if cur.parent_id else None
                continue
            if cur.excluded or (extra and cur.id in extra):
                return True
            cur = self.by_id.get(cur.parent_id) if cur.parent_id else None
        return False

    def is_effectively_excluded(self, kp_id: int) -> bool:
        return kp_id in self._excluded

    def is_valid_unit(self, kp_id: int) -> bool:
        return kp_id in self.valid_units

    def status_of(self, kp: KnowledgePoint) -> str | None:
        """三态仅学习单元有；容器恒 None。"""
        if kp.id not in self.valid_units:
            return None
        if kp.lighted_at is not None:
            return "lighted"
        if kp.id in self.learning_kps:
            return "learning"
        return "unlearned"

    def subtree_ids(self, kp_id: int) -> set[int]:
        ids: set[int] = set()
        stack = [kp_id]
        while stack:
            cur = stack.pop()
            if cur in ids:
                continue
            ids.add(cur)
            for child in self.children.get(cur, []):
                stack.append(child.id)
        return ids

    def subtree_progress(self, kp_id: int) -> tuple[int, int]:
        lighted = 0
        total = 0
        for kp_id_ in self.subtree_ids(kp_id):
            if kp_id_ in self.valid_units:
                total += 1
                if self.by_id[kp_id_].lighted_at is not None:
                    lighted += 1
        return lighted, total

    def progress(self) -> Progress:
        total = len(self.valid_units)
        lighted = sum(1 for i in self.valid_units if self.by_id[i].lighted_at is not None)
        percent = (lighted / total * 100) if total else None
        return Progress(lighted=lighted, total=total, percent=percent)

    def path_names(self, kp_id: int) -> list[str]:
        names: list[str] = []
        cur = self.by_id.get(kp_id)
        while cur is not None:
            names.insert(0, cur.name)
            cur = self.by_id.get(cur.parent_id) if cur.parent_id else None
        return names


def evidence_kp_ids(db: Session, study_id: int) -> set[int]:
    """学习证据所在节点集合（session/message/quiz/note/lighted 任一，不能只看消息）。"""
    kps = db.query(KnowledgePoint).filter(KnowledgePoint.study_id == study_id).all()
    kp_ids = {k.id for k in kps}
    if not kp_ids:
        return set()
    ids: set[int] = {k.id for k in kps if k.lighted_at is not None}

    def extend(found: Iterable[object]) -> None:
        ids.update(i for i in found if i in kp_ids)

    extend(db.execute(select(Session_.kp_id).where(Session_.kp_id.in_(kp_ids))).scalars())
    extend(db.execute(select(Quiz.kp_id).where(Quiz.kp_id.in_(kp_ids))).scalars())
    extend(db.execute(select(Note.kp_id).where(Note.kp_id.in_(kp_ids))).scalars())
    # message 通过 session 挂 kp；session 存在即已计入（message 必有 session）
    return ids


def subtree_has_evidence(db: Session, study_id: int, kp_ids: set[int]) -> bool:
    """目标子树是否存在任一学习证据（决策 #29）。"""
    if not kp_ids:
        return False
    queries = (
        db.query(KnowledgePoint.id).filter(
            KnowledgePoint.id.in_(kp_ids), KnowledgePoint.lighted_at.is_not(None)
        ),
        db.query(Session_.id).filter(Session_.kp_id.in_(kp_ids)),
        db.query(Quiz.id).filter(Quiz.kp_id.in_(kp_ids)),
        db.query(Note.id).filter(Note.kp_id.in_(kp_ids)),
    )
    return any(q.first() is not None for q in queries)
