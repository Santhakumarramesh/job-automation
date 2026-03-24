"""job_idempotency table for IDEMPOTENCY_USE_DB (Phase 4.2.1)

Revision ID: tracker_0005
Revises: tracker_0004
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context as alembic_context
from alembic import op

revision: str = "tracker_0005"
down_revision: Union[str, None] = "tracker_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_table() -> None:
    op.create_table(
        "job_idempotency",
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("key_digest", sa.Text(), nullable=False),
        sa.Column("job_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id", "key_digest"),
    )


def upgrade() -> None:
    if alembic_context.is_offline_mode():
        _create_table()
        return
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if insp.has_table("job_idempotency"):
        return
    _create_table()


def downgrade() -> None:
    op.drop_table("job_idempotency")
