"""V0.1.1：Study 增三列 + planning_proposals 表（V0.1.1 技术设计 §5）。

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-23
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op
from app.models import DEFAULT_LEARNING_GOAL, PlanningProposal

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

NEW_COLUMNS = (
    sa.Column("use_ai_planning", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    sa.Column("planned_days", sa.Integer(), nullable=False, server_default=sa.text("10")),
    sa.Column("learning_goal", sa.Text(), nullable=False, server_default=DEFAULT_LEARNING_GOAL),
)


def upgrade() -> None:
    # 0001 用 create_all 建「当前」模型：全新库走到这里时新结构已存在，只有 V0.1 旧库需要补
    bind = op.get_bind()
    existing = {c["name"] for c in sa.inspect(bind).get_columns("studies")}
    for col in NEW_COLUMNS:
        if col.name not in existing:
            op.add_column("studies", col)

    PlanningProposal.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    PlanningProposal.__table__.drop(bind=op.get_bind(), checkfirst=True)
    for col in NEW_COLUMNS:
        op.drop_column("studies", col.name)
