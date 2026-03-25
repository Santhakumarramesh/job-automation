"""applications.job_state — indexed decision.job_state (v0.1 contract)

Revision ID: tracker_0008
Revises: tracker_0007
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context as alembic_context
from alembic import op

revision: str = "tracker_0008"
down_revision: Union[str, None] = "tracker_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if alembic_context.is_offline_mode():
        op.add_column(
            "applications",
            sa.Column("job_state", sa.Text(), server_default="", nullable=False),
        )
        return
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c["name"] for c in insp.get_columns("applications")}
    if "job_state" not in cols:
        op.add_column(
            "applications",
            sa.Column("job_state", sa.Text(), server_default="", nullable=False),
        )


def downgrade() -> None:
    if alembic_context.is_offline_mode():
        op.drop_column("applications", "job_state")
        return
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c["name"] for c in insp.get_columns("applications")}
    if "job_state" in cols:
        op.drop_column("applications", "job_state")
