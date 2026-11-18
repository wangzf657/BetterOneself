"""按数据模型.md 注册全部模型;导入即建表元数据。"""

from app.models.card import Card, ReviewLog
from app.models.knowledge import KnowledgePoint, KnowledgeRef, KpDependency
from app.models.learning import LearningSession, Message, Quiz
from app.models.mastery import MasteryEvent, Summary
from app.models.plan import Plan, PlanEvent, Task
from app.models.setting import Setting, UsageDay
from app.models.source import Source, SourceChunk, StudySource
from app.models.study import Study

__all__ = [
    "Card",
    "KpDependency",
    "KnowledgePoint",
    "KnowledgeRef",
    "LearningSession",
    "MasteryEvent",
    "Message",
    "Plan",
    "PlanEvent",
    "Quiz",
    "ReviewLog",
    "Setting",
    "Source",
    "SourceChunk",
    "Study",
    "StudySource",
    "Summary",
    "Task",
    "UsageDay",
]
