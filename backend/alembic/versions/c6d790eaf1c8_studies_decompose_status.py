"""studies decompose status

Revision ID: c6d790eaf1c8
Revises: 5df6bed231eb
Create Date: 2026-11-19 12:24:28.492597

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c6d790eaf1c8"
down_revision: Union[str, Sequence[str], None] = "5df6bed231eb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """SQLite 加列走 batch 模式(技术总纲 5.4)。"""
    with op.batch_alter_table("studies") as batch:
        batch.add_column(
            sa.Column("decompose_status", sa.String(length=16), nullable=False,
                      server_default="idle")
        )
        batch.add_column(sa.Column("decompose_error", sa.String(length=500), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("studies") as batch:
        batch.drop_column("decompose_error")
        batch.drop_column("decompose_status")
