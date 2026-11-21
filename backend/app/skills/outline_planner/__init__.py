"""outline_planner skill（技术方案 §6）：章节摘要 + 全书拟大纲。"""

from app.skills.outline_planner.skill import (
    PlanOp,
    PlanResult,
    SplitPart,
    parse_plan,
    plan,
    summarize_chapter,
)

__all__ = ["PlanOp", "PlanResult", "SplitPart", "parse_plan", "plan", "summarize_chapter"]
