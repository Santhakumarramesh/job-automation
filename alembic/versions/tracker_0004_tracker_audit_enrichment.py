"""ATS provider, ceiling, address label, package stats on applications.

Revision ID: tracker_0004
Revises: tracker_0003
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context as alembic_context
from alembic import op

revision: str = "tracker_0004"
down_revision: Union[str, None] = "tracker_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_COLS = (
    ("ats_provider", sa.Text()),
    ("ats_provider_apply_target", sa.Text()),
    ("truth_safe_ats_ceiling", sa.Text()),
    ("selected_address_label", sa.Text()),
    ("package_field_stats", sa.Text()),
)


def upgrade() -> None:
    if alembic_context.is_offline_mode():
        for name, typ in _NEW_COLS:
            op.add_column("applications", sa.Column(name, typ, nullable=True))
        return
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c["name"] for c in insp.get_columns("applications")}
    for name, typ in _NEW_COLS:
        if name not in cols:
            op.add_column("applications", sa.Column(name, typ, nullable=True))


def downgrade() -> None:
    if alembic_context.is_offline_mode():
        for name, _ in reversed(_NEW_COLS):
            op.drop_column("applications", name)
        return
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c["name"] for c in insp.get_columns("applications")}
    for name, _ in reversed(_NEW_COLS):
        if name in cols:
            op.drop_column("applications", name)
