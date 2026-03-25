"""task_state_snapshots for TASK_STATE_BACKEND=db (Phase 4.2.2)

Revision ID: tracker_0006
Revises: tracker_0005
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context as alembic_context
from alembic import op

revision: str = "tracker_0006"
down_revision: Union[str, None] = "tracker_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_table() -> None:
    op.create_table(
        "task_state_snapshots",
        sa.Column("task_id", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("task_id"),
    )


def upgrade() -> None:
    if alembic_context.is_offline_mode():
        _create_table()
        return
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if insp.has_table("task_state_snapshots"):
        return
    _create_table()


def downgrade() -> None:
    op.drop_table("task_state_snapshots")
