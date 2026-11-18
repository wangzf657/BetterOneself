"""内嵌测验(M3-04):按知识点出题、判分;错题自动沉淀卡片(M3-05)。"""

import json
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import llm, prompts
from app.models import KnowledgeRef, LearningSession, Quiz, SourceChunk
from app.services import mastery, review


class QuizGenItem(BaseModel):
    q_type: Literal["objective", "short_answer"]
    question: str
    options: list[str] = Field(default_factory=list)
    answer: str
    chunk_id: int | None = None


class QuizGenOut(BaseModel):
    quizzes: list[QuizGenItem]


class QuizGradeOut(BaseModel):
    is_correct: bool
    feedback: str


def generate_for_session(db: Session, session: LearningSession) -> list[Quiz]:
    if session.kp_id is None:
        raise ValueError("会话未绑定知识点,无法出题")

    kp_name = _kp_name(db, session)
    chunks = db.execute(
        select(SourceChunk)
        .join(KnowledgeRef, KnowledgeRef.chunk_id == SourceChunk.id)
        .where(KnowledgeRef.kp_id == session.kp_id)
        .order_by(SourceChunk.seq)
    ).scalars()
    chunk_payload = [
        {"chunk_id": c.id, "heading_path": c.heading_path, "content": c.content}
        for c in chunks
    ]
    if not chunk_payload:
        raise ValueError("知识点没有来源切片,无法出题")

    out = llm.parse_json(prompts.quiz_gen_messages(kp_name, chunk_payload), QuizGenOut)
    rows = []
    for item in out.quizzes:
        rows.append(
            Quiz(
                session_id=session.id,
                kp_id=session.kp_id,
                q_type=item.q_type,
                question=item.question,
                options_json=json.dumps(item.options, ensure_ascii=False) if item.options else None,
                answer=item.answer,
                chunk_id=item.chunk_id,
            )
        )
    db.add_all(rows)
    db.commit()
    for r in rows:
        db.refresh(r)
    return rows


def _kp_name(db: Session, session: LearningSession) -> str:
    from app.models import KnowledgePoint

    kp = db.get(KnowledgePoint, session.kp_id)
    return kp.name if kp else ""


def grade(db: Session, quiz: Quiz, user_answer: str) -> Quiz:
    quiz.user_answer = user_answer
    if quiz.q_type == "objective":
        quiz.is_correct = _norm(user_answer) == _norm(quiz.answer)
    else:
        out = llm.parse_json(
            prompts.quiz_grade_messages(quiz.question, quiz.answer, user_answer), QuizGradeOut
        )
        quiz.is_correct = out.is_correct
        quiz.ai_feedback = out.feedback
    db.commit()
    db.refresh(quiz)

    if quiz.is_correct is False:
        _create_card_from_wrong(db, quiz)
    mastery.record_quiz_result(db, quiz)
    return quiz


def _create_card_from_wrong(db: Session, quiz: Quiz) -> None:
    """错题自动生成卡片:正面问题,背面答案+源引用(M3-05)。"""
    session = db.get(LearningSession, quiz.session_id)
    if session is None:
        return
    back = quiz.answer
    if quiz.chunk_id:
        chunk = db.get(SourceChunk, quiz.chunk_id)
        if chunk and chunk.heading_path:
            back = f"{quiz.answer}\n\n> 来源:{chunk.heading_path}"
    review.create_card(
        db,
        study_id=session.study_id,
        kp_id=quiz.kp_id,
        front=quiz.question,
        back_md=back,
        chunk_id=quiz.chunk_id,
        origin="auto_quiz",
    )


def _norm(text: str) -> str:
    return "".join(text.split()).lower()
