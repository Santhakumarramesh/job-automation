"""application_decision JSON column on applications (v0.1 decision snapshot)

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


def upgrade() -> None:
    if alembic_context.is_offline_mode():
        op.add_column(
            "applications",
            sa.Column("application_decision", sa.Text(), nullable=True),
        )
        return
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c["name"] for c in insp.get_columns("applications")}
    if "application_decision" not in cols:
        op.add_column(
            "applications",
            sa.Column("application_decision", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    if alembic_context.is_offline_mode():
        op.drop_column("applications", "application_decision")
        return
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c["name"] for c in insp.get_columns("applications")}
    if "application_decision" in cols:
        op.drop_column("applications", "application_decision")
