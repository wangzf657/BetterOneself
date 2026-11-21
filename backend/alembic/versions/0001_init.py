"""init：建全部表 + sqlite-vec 虚表（空库起步，数据模型 §1）。

Revision ID: 0001
Revises:
Create Date: 2026-11-21
"""

from __future__ import annotations

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.core.db import init_db

    init_db(op.get_bind())


def downgrade() -> None:
    from app.models import Base

    Base.metadata.drop_all(op.get_bind())
    op.execute("DROP TABLE IF EXISTS vec_chunks")
