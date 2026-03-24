"""follow-up reminder columns on applications (Phase 12)

Revision ID: tracker_0002
Revises: tracker_0001
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context as alembic_context
from alembic import op

revision: str = "tracker_0002"
down_revision: Union[str, None] = "tracker_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_columns() -> None:
    op.add_column("applications", sa.Column("follow_up_at", sa.Text(), nullable=True))
    op.add_column("applications", sa.Column("follow_up_status", sa.Text(), nullable=True))
    op.add_column("applications", sa.Column("follow_up_note", sa.Text(), nullable=True))


def upgrade() -> None:
    if alembic_context.is_offline_mode():
        _add_columns()
        return
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c["name"] for c in insp.get_columns("applications")}
    if "follow_up_at" not in cols:
        op.add_column("applications", sa.Column("follow_up_at", sa.Text(), nullable=True))
    if "follow_up_status" not in cols:
        op.add_column("applications", sa.Column("follow_up_status", sa.Text(), nullable=True))
    if "follow_up_note" not in cols:
        op.add_column("applications", sa.Column("follow_up_note", sa.Text(), nullable=True))


def downgrade() -> None:
    if alembic_context.is_offline_mode():
        op.drop_column("applications", "follow_up_note")
        op.drop_column("applications", "follow_up_status")
        op.drop_column("applications", "follow_up_at")
        return
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c["name"] for c in insp.get_columns("applications")}
    for name in ("follow_up_note", "follow_up_status", "follow_up_at"):
        if name in cols:
            op.drop_column("applications", name)
