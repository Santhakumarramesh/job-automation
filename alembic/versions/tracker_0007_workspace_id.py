"""applications.workspace_id (Phase 4.1.2)

Revision ID: tracker_0007
Revises: tracker_0006
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context as alembic_context
from alembic import op

revision: str = "tracker_0007"
down_revision: Union[str, None] = "tracker_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if alembic_context.is_offline_mode():
        op.add_column(
            "applications",
            sa.Column("workspace_id", sa.Text(), server_default="", nullable=False),
        )
        return
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c["name"] for c in insp.get_columns("applications")}
    if "workspace_id" in cols:
        return
    op.add_column(
        "applications",
        sa.Column("workspace_id", sa.Text(), server_default="", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("applications", "workspace_id")
