"""Pydantic 契约（前端类型由 OpenAPI 生成，接口设计 §1）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ProgressInfo(BaseModel):
    lighted: int
    total: int
    percent: float | None = None


class LastKp(BaseModel):
    id: int
    name: str
    status: str | None = None


class StudyItem(BaseModel):
    id: int
    name: str
    source_id: int | None = None
    source_type: str | None = None
    parse_status: str | None = None
    parse_error: str | None = None
    outline_status: str
    use_ai_planning: bool = False
    progress: ProgressInfo | None = None
    last_learned_at: datetime | None = None
    last_kp: LastKp | None = None


class StudyDetail(BaseModel):
    id: int
    name: str
    scheme: str
    outline_thesis: str | None = None
    outline_status: str
    use_ai_planning: bool = False
    planned_days: int = 10
    learning_goal: str = ""
    source_type: str | None = None


class StudyPatch(BaseModel):
    name: str | None = None
    scheme: Literal["guided", "lecture", "drill"] | None = None


class RecentQuiz(BaseModel):
    quiz_id: int
    passed: bool | None = None
    correct_count: int | None = None
    pass_line: int
    answered_at: datetime | None = None


class KnowledgeNode(BaseModel):
    id: int
    name: str
    sort_order: int
    parent_id: int | None = None
    is_chapter: bool
    is_learning_unit: bool
    origin: str
    confidence: float
    confidence_basis: str
    planning_note: str | None = None
    excluded: bool
    exclusion_reason: str | None = None
    status: Literal["unlearned", "learning", "lighted"] | None = None
    lighted_at: datetime | None = None
    lighted_by_quiz_id: int | None = None
    lighted_count: int | None = None
    valid_total: int | None = None
    recent_quiz: RecentQuiz | None = None
    children: list[KnowledgeNode] = Field(default_factory=list)


class KnowledgeTree(BaseModel):
    study_id: int
    progress: ProgressInfo | None = None
    nodes: list[KnowledgeNode]


class AdjustSummary(BaseModel):
    parts: int
    excluded: int
    split: int
    merged: int
    organized: int
    applied: int
    skipped: int
    planned: int


class OutlineStatus(BaseModel):
    status: str
    error: str | None = None
    thesis: str | None = None
    adjust_summary: AdjustSummary | None = None
    low_confidence_count: int


class OutlineEventItem(BaseModel):
    id: int
    event_type: str
    actor: str
    kp_id: int | None = None
    kp_name: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ExcludeImpact(BaseModel):
    kp_id: int
    kp_name: str
    lighted_affected: int
    progress_before: ProgressInfo | None = None
    progress_after: ProgressInfo | None = None


class KpMutationResult(BaseModel):
    kp: KnowledgeNode
    progress_before: ProgressInfo | None = None
    progress_after: ProgressInfo | None = None


class RenameBody(BaseModel):
    name: str


class ExcludeBody(BaseModel):
    reason: str | None = None


class RestorePreview(BaseModel):
    can_restore: bool
    planning_running: bool
    evidence_kps: list[str]
    ai_adjustments: int
    revoked_renames: int
    revoked_exclusions: int


class RestoreResult(BaseModel):
    removed: int
    restored: int
    ai_adjustments: int = 0
    revoked_renames: int
    revoked_exclusions: int
    progress_before: ProgressInfo | None = None
    progress_after: ProgressInfo | None = None


class PhaseParse(BaseModel):
    status: str
    error: str | None = None


class PlanStage(BaseModel):
    phase: str  # summary（章摘要 x/y）/ plan（全局规划）
    done: int
    total: int


class PhaseOutline(BaseModel):
    status: str
    error: str | None = None
    thesis: str | None = None
    adjust_summary: dict[str, int] | None = None
    stage: PlanStage | None = None
    ai_planning: bool = False


class PhaseEmbedding(BaseModel):
    status: str
    done: int
    total: int
    error: str | None = None


class PipelineProgress(BaseModel):
    parse: PhaseParse
    outline: PhaseOutline
    embedding: PhaseEmbedding


class LaneCheck(BaseModel):
    ok: bool
    reason: Literal["not_configured", "request_failed", "dim_mismatch"] | None = None
    detail: str | None = None


class PrecheckBody(BaseModel):
    lanes: list[Literal["embedding", "llm"]] | None = None


class PrecheckResult(BaseModel):
    embedding: LaneCheck | None = None
    llm: LaneCheck | None = None


class ReembedResult(BaseModel):
    status: str  # reembed_started / precheck_failed
    embedding: LaneCheck


class Estimate(BaseModel):
    embedding_tokens: int
    planning_tokens: list[int]  # [下限, 上限]


class PlanningStartBody(BaseModel):
    planned_days: int = Field(ge=1, le=365)
    learning_goal: str = Field(min_length=1, max_length=200)

    @field_validator("learning_goal")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("学习目标不能为空白")
        return v


class ProposalOp(BaseModel):
    op: str
    node_id: int | None = None
    node_ids: list[int] | None = None
    chapter_ids: list[int] | None = None
    title: str | None = None
    reason: str | None = None
    parts: list[dict[str, Any]] | None = None
    targets: list[str]
    flagged: bool = False
    flag_reason: str | None = None


class PlanningProposalView(BaseModel):
    proposal_id: int
    thesis: str
    created_at: datetime
    operations: list[ProposalOp]


class ProposalApplyBody(BaseModel):
    proposal_id: int
    selected: list[int] = Field(min_length=1)


class ProposalApplyResult(BaseModel):
    status: str
    adjust_summary: AdjustSummary
    skipped: list[dict[str, Any]]


class ProposalDeclineBody(BaseModel):
    proposal_id: int


class ProposalDeclineResult(BaseModel):
    status: str


class DeleteImpact(BaseModel):
    sessions: int
    quizzes: int
    lighted: int
    notes: int


class SessionCreate(BaseModel):
    kp_id: int
    scheme: Literal["guided", "lecture", "drill"] | None = None


class SchemePatch(BaseModel):
    scheme: Literal["guided", "lecture", "drill"]


class MessageRef(BaseModel):
    no: int
    chunk_id: int
    title: str
    location: dict[str, Any]
    quote: str


class MessageItem(BaseModel):
    id: int
    role: str
    content: str
    refs: list[MessageRef] = Field(default_factory=list)
    stopped: bool = False
    created_at: datetime


class SessionInfo(BaseModel):
    id: int
    study_id: int
    kp_id: int
    kp_name: str | None = None
    kp_path: list[str] = Field(default_factory=list)
    scheme: str
    excluded: bool


class QuizQuestionPublic(BaseModel):
    no: int
    type: str
    graded: bool
    stem: str
    options: list[str] | None = None


class QuizPublic(BaseModel):
    quiz_id: int
    session_id: int
    kp_id: int
    created_at: datetime | None = None
    question_count: int
    graded_count: int
    practice_count: int
    pass_line: int
    answered_at: datetime | None = None
    questions: list[QuizQuestionPublic]
    coverage: list[dict[str, Any]] = Field(default_factory=list)


class SessionDetail(BaseModel):
    session: SessionInfo
    messages: list[MessageItem]
    quizzes: list[dict[str, Any]]


class ChatBody(BaseModel):
    content: str


class QuizAnswerBody(BaseModel):
    answers: list[dict[str, Any]]


class ChunkPayload(BaseModel):
    id: int
    title: str
    content: str
    location: dict[str, Any]
    level_path: str | None = None


class NodeContent(BaseModel):
    kp_id: int
    kp_name: str
    chunks: list[ChunkPayload]
    source_id: int | None = None  # 原文视图按主文件取原文件与资产（B6-07）
    source_type: str | None = None


class ChunkDetail(BaseModel):
    chunk: ChunkPayload
    source_id: int


class NotePayload(BaseModel):
    kp_id: int
    content_md: str
    updated_at: datetime | None = None


class NotePut(BaseModel):
    content_md: str


class SettingsGroup(BaseModel):
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None


class EmbedSettings(SettingsGroup):
    status: str | None = None
    error: str | None = None
    note: str | None = None


class SettingsPayload(BaseModel):
    llm: SettingsGroup
    embed: EmbedSettings


class SettingsPut(BaseModel):
    llm: SettingsGroup | None = None
    embed: SettingsGroup | None = None


class UsageRow(BaseModel):
    date: str
    scene: str
    requests: int
    prompt_tokens: int
    completion_tokens: int
