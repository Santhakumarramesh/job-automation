"""interview_stage and offer_outcome on applications (Phase 13 pipeline)

Revision ID: tracker_0003
Revises: tracker_0002
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context as alembic_context
from alembic import op

revision: str = "tracker_0003"
down_revision: Union[str, None] = "tracker_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_columns() -> None:
    op.add_column("applications", sa.Column("interview_stage", sa.Text(), nullable=True))
    op.add_column("applications", sa.Column("offer_outcome", sa.Text(), nullable=True))


def upgrade() -> None:
    if alembic_context.is_offline_mode():
        _add_columns()
        return
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c["name"] for c in insp.get_columns("applications")}
    if "interview_stage" not in cols:
        op.add_column("applications", sa.Column("interview_stage", sa.Text(), nullable=True))
    if "offer_outcome" not in cols:
        op.add_column("applications", sa.Column("offer_outcome", sa.Text(), nullable=True))


def downgrade() -> None:
    if alembic_context.is_offline_mode():
        op.drop_column("applications", "offer_outcome")
        op.drop_column("applications", "interview_stage")
        return
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c["name"] for c in insp.get_columns("applications")}
    for name in ("offer_outcome", "interview_stage"):
        if name in cols:
            op.drop_column("applications", name)
