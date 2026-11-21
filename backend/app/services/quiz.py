"""测验与点亮服务（B4、决策 #28/30）：固定通过线、幂等、判分事务、达线即点亮。"""

from __future__ import annotations

import json
from typing import Any, cast

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.errors import LLMUnavailable, NotFound, Validation
from app.models import (
    KnowledgePoint,
    KnowledgeRef,
    Quiz,
    Session_,
    SourceChunk,
    Study,
    utcnow,
)
from app.services.tree_core import TreeIndex
from app.skills.quiz import QuizDraft, QuizQuestionDraft


def _touch_pointers(db: Session, session: Session_) -> None:
    """学习指针：由最近的 message 写入或 quiz 提交更新（技术方案 §7.1）。"""
    study = db.get(Study, session.study_id)
    if study is not None:
        study.last_kp_id = session.kp_id
        study.last_learned_at = utcnow()


def _llm_ready(db: Session) -> bool:
    from app.core.config import get_config
    from app.core.llm import llm_configured

    return get_config().llm_stub or llm_configured(db)

# 固定通过线映射（决策 #28）：判分只比对不重算；LLM 与前端均不参与判定
PASS_LINE: dict[int, int] = {3: 2, 4: 3, 5: 4}
GRADED_RANGE = (3, 5)
DUP_FAIL_DETAIL = "本次出题失败（题目与历史重复），请稍后再试"


def _quiz_or_404(db: Session, quiz_id: int) -> Quiz:
    quiz = db.get(Quiz, quiz_id)
    if quiz is None:
        raise NotFound("测验不存在")
    return quiz


def _node_sources(db: Session, kp_id: int) -> list[dict[str, Any]]:
    rows = (
        db.query(KnowledgeRef, SourceChunk)
        .join(SourceChunk, SourceChunk.id == KnowledgeRef.chunk_id)
        .filter(KnowledgeRef.kp_id == kp_id)
        .order_by(SourceChunk.sort_order)
        .all()
    )
    return [
        {"chunk_id": c.id, "title": c.title, "content": c.content[:SOURCE_CAP],
         "location": json.loads(c.location)}
        for _r, c in rows
    ]


SOURCE_CAP = 3000
TOTAL_SOURCE_BUDGET = 15000


def _history_stems(db: Session, kp_id: int) -> list[str]:
    stems: list[str] = []
    for q in (
        db.query(Quiz).filter(Quiz.kp_id == kp_id).order_by(Quiz.id).all()
    ):
        try:
            data = json.loads(q.questions_json)
            stems.extend(item.get("stem", "") for item in data.get("questions", []))
        except json.JSONDecodeError:
            continue
    return [s for s in stems if s]


def _validate_draft(
    draft: QuizDraft, graded_target: int, practice: bool, source_count: int
) -> list[QuizQuestionDraft]:
    """契约校验：3–5 计分 + 至多 1 练习；refs 只能指向传入 sources。"""
    questions = sorted(draft.questions, key=lambda q: (not q.graded, q.no))
    graded = [q for q in questions if q.graded]
    shorts = [q for q in questions if not q.graded]
    if len(graded) != graded_target or not (GRADED_RANGE[0] <= len(graded) <= GRADED_RANGE[1]):
        raise Validation(f"客观计分题须为 {GRADED_RANGE[0]}–{GRADED_RANGE[1]} 道")
    if len(shorts) > 1:
        raise Validation("简答练习至多 1 道")
    if practice and not shorts:
        raise Validation("缺少简答练习题")
    if not practice and shorts:
        raise Validation("不应包含简答练习题")
    for q in questions:
        if not q.stem.strip():
            raise Validation("题干不能为空")
        if q.graded:
            if q.type == "choice":
                if not q.options or len(q.options) < 3:
                    raise Validation("单选题选项不足")
                letters = [o.strip()[0].upper() for o in q.options if o.strip()]
                if not q.answer or str(q.answer).strip().upper()[:1] not in letters:
                    raise Validation("单选题答案不在选项中")
            elif q.type == "judge":
                if not isinstance(q.answer, bool):
                    raise Validation("判断题答案必须是 true/false")
            else:
                raise Validation("计分题只能是单选或判断")
            if not (q.explanation and q.explanation.strip()):
                raise Validation("计分题缺少解析")
        else:
            if q.type != "short":
                raise Validation("练习题必须是简答")
            if not (q.reference_answer and q.reference_answer.strip()):
                raise Validation("练习题缺少参考答案")
        for n in q.refs:
            if not (1 <= n <= source_count):
                raise Validation("题目引用了不存在的来源编号")
    # 重编号：计分题在前、练习在后
    for i, q in enumerate(questions, start=1):
        q.no = i
    return questions


def serialize_public(db: Session, quiz: Quiz) -> dict[str, Any]:
    """未提交测验公开面：不含答案、解析与答案 refs（B4-01 反例）。"""
    data = json.loads(quiz.questions_json)
    questions = data.get("questions", [])
    graded = [q for q in questions if q.get("graded")]
    practice = [q for q in questions if not q.get("graded")]
    return {
        "quiz_id": quiz.id,
        "session_id": quiz.session_id,
        "kp_id": quiz.kp_id,
        "created_at": quiz.created_at,
        "question_count": len(questions),
        "graded_count": len(graded),
        "practice_count": len(practice),
        "pass_line": quiz.pass_line,
        "answered_at": quiz.answered_at,
        "questions": [
            {
                "no": q.get("no"),
                "type": q.get("type"),
                "graded": q.get("graded"),
                "stem": q.get("stem"),
                "options": q.get("options"),
            }
            for q in questions
        ],
        "coverage": data.get("coverage", []),
    }


def serialize_answered(db: Session, quiz: Quiz) -> dict[str, Any]:
    base = serialize_public(db, quiz)
    submitted = json.loads(quiz.submitted_answers_json or "[]")
    per_question = json.loads(quiz.grading_results_json or "[]")
    return {
        **base,
        "created_at": quiz.created_at,
        "answered_at": quiz.answered_at,
        "correct_count": quiz.correct_count,
        "passed": quiz.passed,
        "submitted_answers": submitted,
        "per_question": per_question,
    }


def quizzes_of_session(db: Session, session_id: int) -> list[dict[str, Any]]:
    quizzes = (
        db.query(Quiz).filter(Quiz.session_id == session_id).order_by(Quiz.id).all()
    )
    return [
        serialize_answered(db, q) if q.answered_at else serialize_public(db, q)
        for q in quizzes
    ]


def quizzes_of_kp(db: Session, kp_id: int) -> list[dict[str, Any]]:
    """历次测验回看（B4-04）：一律 QuizAnswered 面。"""
    quizzes = db.query(Quiz).filter(Quiz.kp_id == kp_id).order_by(Quiz.id.desc()).all()
    return [serialize_answered(db, q) for q in quizzes if q.answered_at]


async def generate_quiz(db: Session, session: Session_) -> dict[str, Any]:
    """生成一组：幂等（进行中直接返回）；历史去重；二次重复终态失败（P1-03、B4-02）。"""
    from app.skills.quiz import generate as skill_generate
    from app.skills.quiz import parse_quiz

    kp = db.get(KnowledgePoint, session.kp_id)
    assert kp is not None
    index = TreeIndex(db, session.study_id)
    if kp.excluded or index.is_effectively_excluded(kp.id):
        raise Validation("该节点已排除：不能生成正式测验，历史测验只读可回看")
    if not index.is_valid_unit(kp.id):
        raise Validation("该节点当前不能测验（容器节点或原文引用未就绪）")

    open_quiz = (
        db.query(Quiz)
        .filter(Quiz.kp_id == session.kp_id, Quiz.answered_at.is_(None))
        .one_or_none()
    )
    if open_quiz is not None:
        return serialize_public(db, open_quiz)  # 双击与断连重试不重复生成

    if not _llm_ready(db):
        from app.core.errors import LLMNotConfigured

        raise LLMNotConfigured()

    sources = _node_sources(db, kp.id)
    budget: list[dict[str, Any]] = []
    used = 0
    for s in sources:
        if used + len(s["content"]) > TOTAL_SOURCE_BUDGET:
            continue
        budget.append(s)
        used += len(s["content"])

    history = _history_stems(db, kp.id)
    graded_target = 4
    draft: QuizDraft | None = None
    questions: list[QuizQuestionDraft] | None = None
    for _attempt in range(2):
        payload = {
            "node_title": kp.name,
            "node_path": index.path_names(kp.id),
            "scheme": session.scheme,
            "graded_count": graded_target,
            "practice": True,
            "history_stems": history,
            "sources": budget,
        }
        raw = await skill_generate(db, payload)
        try:
            draft = parse_quiz(raw)
            questions = _validate_draft(draft, graded_target, True, len(budget))
        except Validation:
            draft = None
            questions = None
            continue
        stems = [q.stem for q in questions]
        if any(s in history for s in stems) or len(set(stems)) != len(stems):
            draft = None
            questions = None
            continue  # 完全重复 → 重试一次
        break
    if questions is None:
        raise LLMUnavailable(DUP_FAIL_DETAIL)  # retryable=True 由错误类型默认携带

    graded = [q for q in questions if q.graded]
    pass_line = PASS_LINE[len(graded)]

    public_questions = [
        {
            "no": q.no,
            "type": q.type,
            "graded": q.graded,
            "stem": q.stem,
            "options": q.options,
        }
        for q in questions
    ]
    coverage = [
        {"no": q.no, "dimension": q.dimension or ("细节理解与辨析" if q.graded else "练习")}
        for q in questions
        if q.graded
    ]
    answers = [
        {
            "no": q.no,
            "answer": (str(q.answer).strip().upper()[:1] if q.type == "choice" else q.answer),
            "explanation": q.explanation,
            "reference_answer": q.reference_answer,
            "chunk_ids": [budget[n - 1]["chunk_id"] for n in q.refs],
        }
        for q in questions
    ]
    quiz = Quiz(
        study_id=session.study_id,
        kp_id=session.kp_id,
        session_id=session.id,
        questions_json=json.dumps(
            {"questions": public_questions, "coverage": coverage}, ensure_ascii=False
        ),
        answers_json=json.dumps(answers, ensure_ascii=False),
        pass_line=pass_line,
    )
    db.add(quiz)
    db.commit()
    return serialize_public(db, quiz)


def _chunk_refs(db: Session, chunk_ids: list[int]) -> list[dict[str, Any]]:
    if not chunk_ids:
        return []
    chunks = db.query(SourceChunk).filter(SourceChunk.id.in_(chunk_ids)).all()
    by_id = {c.id: c for c in chunks}
    return [
        {
            "chunk_id": cid,
            "title": by_id[cid].title,
            "location": json.loads(by_id[cid].location),
            "quote": by_id[cid].content[:100],
        }
        for cid in chunk_ids
        if cid in by_id
    ]


async def answer_quiz(db: Session, quiz_id: int, answers: list[dict[str, Any]]) -> dict[str, Any]:
    """整组提交：条件更新原子认领；代码判定；判分与点亮同事务（P1-03、决策 #30）。"""
    from app.skills.quiz import comment_short_answer

    quiz = _quiz_or_404(db, quiz_id)
    if quiz.answered_at is not None:
        return _answered_with_lighted(db, quiz, already=True)

    from sqlalchemy.engine import CursorResult

    claimed = cast(
        CursorResult[Any],
        db.execute(
            update(Quiz)
            .where(Quiz.id == quiz_id, Quiz.answered_at.is_(None))
            .values(answered_at=utcnow())
        ),
    ).rowcount
    if not claimed:
        db.rollback()
        quiz = _quiz_or_404(db, quiz_id)
        return _answered_with_lighted(db, quiz, already=True)

    questions = json.loads(quiz.questions_json)["questions"]
    server_answers = {a["no"]: a for a in json.loads(quiz.answers_json)}
    empty_answer: dict[str, Any] = {}
    submitted_by_no = {a.get("no"): a for a in answers}

    kp = db.get(KnowledgePoint, quiz.kp_id)
    assert kp is not None
    was_lighted = kp.lighted_at is not None

    per_question: list[dict[str, Any]] = []
    submitted: list[dict[str, Any]] = []
    correct_count = 0
    for q in questions:
        no = q["no"]
        ans = submitted_by_no.get(no)
        server = server_answers.get(no) or empty_answer
        entry: dict[str, Any] = {
            "no": no,
            "graded": q.get("graded", True),
            "refs": _chunk_refs(db, server.get("chunk_ids", []) if server else []),
        }
        if ans is not None:
            submitted.append(
                {"no": no, **({"choice": ans["choice"]} if "choice" in ans
                   else {"text": ans.get("text", "")})}
            )
        if q.get("graded", True):
            if ans is None:
                correct = False
            elif q["type"] == "choice":
                correct = (
                    isinstance(ans.get("choice"), str)
                    and ans["choice"].strip().upper()[:1]
                    == str(server.get("answer", "")).strip().upper()[:1]
                )
            else:  # judge
                correct = ans.get("choice") is not None and ans["choice"] == server.get("answer")
            if correct:
                correct_count += 1
            entry["correct"] = correct
            entry["answer"] = server.get("answer")
            entry["explanation"] = server.get("explanation")
        else:
            user_text = (ans or {}).get("text", "")
            comment = None
            sources_text = "\n\n".join(
                f"[{i}] {c.title}\n{c.content}"
                for i, c in enumerate(
                    db.query(SourceChunk)
                    .filter(
                        SourceChunk.id.in_(server.get("chunk_ids", []) if server else [])
                    )
                    .all(),
                    start=1,
                )
            )
            if user_text.strip():
                for _ in range(2):  # 评语失败重试一次，再降级为可读说明
                    try:
                        comment = await comment_short_answer(
                            db,
                            stem=q["stem"],
                            reference_answer=server.get("reference_answer"),
                            user_answer=user_text,
                            sources_text=sources_text,
                        )
                        break
                    except Exception:
                        continue
            entry["comment"] = comment or "（评语暂不可用：本次未生成，可在回看中重试）"
        per_question.append(entry)

    passed = correct_count >= quiz.pass_line
    quiz.submitted_answers_json = json.dumps(submitted, ensure_ascii=False)
    quiz.grading_results_json = json.dumps(per_question, ensure_ascii=False)
    quiz.correct_count = correct_count
    quiz.passed = passed

    # 达线即点亮：判分事务内写首次通过证据（B4-03；已点亮不触碰）
    if passed and kp.lighted_at is None:
        kp.lighted_at = utcnow()
        kp.lighted_by_quiz_id = quiz.id

    session = db.get(Session_, quiz.session_id)
    if session is not None:
        _touch_pointers(db, session)
    db.commit()
    return _answered_with_lighted(db, quiz, already=was_lighted)


def _answered_with_lighted(db: Session, quiz: Quiz, *, already: bool) -> dict[str, Any]:
    kp = db.get(KnowledgePoint, quiz.kp_id)
    data = serialize_answered(db, quiz)
    data["lighted"] = (
        {
            "kp_name": kp.name if kp else None,
            "lighted_at": kp.lighted_at if kp else None,
            "already_lighted": already,
        }
        if kp
        else None
    )
    return data


def lighting_evidence(db: Session, kp_id: int) -> dict[str, Any] | None:
    """点亮下钻：首次通过测验证据（B5-01）。"""
    kp = db.get(KnowledgePoint, kp_id)
    if kp is None or kp.lighted_by_quiz_id is None:
        return None
    quiz = db.get(Quiz, kp.lighted_by_quiz_id)
    if quiz is None:
        return None
    return serialize_answered(db, quiz)


__all__ = [
    "DUP_FAIL_DETAIL",
    "PASS_LINE",
    "answer_quiz",
    "generate_quiz",
    "lighting_evidence",
    "quizzes_of_kp",
    "quizzes_of_session",
    "serialize_answered",
    "serialize_public",
]
