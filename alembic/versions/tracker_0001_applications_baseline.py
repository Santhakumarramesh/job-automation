"""applications table baseline (Postgres tracker)

Revision ID: tracker_0001
Revises:
Create Date: 2025-03-10

If `applications` already exists (e.g. created by services.tracker_db), this revision
no-ops on create but still records the revision in alembic_version.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context as alembic_context
from alembic import op

revision: str = "tracker_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_applications_table() -> None:
    op.create_table(
        "applications",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("job_id", sa.Text(), nullable=True),
        sa.Column("job_url", sa.Text(), nullable=True),
        sa.Column("apply_url", sa.Text(), nullable=True),
        sa.Column("company", sa.Text(), nullable=True),
        sa.Column("position", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("submission_status", sa.Text(), nullable=True),
        sa.Column("easy_apply_confirmed", sa.Text(), nullable=True),
        sa.Column("apply_mode", sa.Text(), nullable=True),
        sa.Column("policy_reason", sa.Text(), server_default=sa.text("''"), nullable=True),
        sa.Column("fit_decision", sa.Text(), nullable=True),
        sa.Column("ats_score", sa.Text(), nullable=True),
        sa.Column("resume_path", sa.Text(), nullable=True),
        sa.Column("cover_letter_path", sa.Text(), nullable=True),
        sa.Column("job_description", sa.Text(), nullable=True),
        sa.Column("applied_at", sa.Text(), nullable=True),
        sa.Column("recruiter_response", sa.Text(), nullable=True),
        sa.Column("screenshots_path", sa.Text(), nullable=True),
        sa.Column("qa_audit", sa.Text(), nullable=True),
        sa.Column(
            "artifacts_manifest",
            sa.Text(),
            server_default=sa.text("'{}'"),
            nullable=True,
        ),
        sa.Column("retry_state", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Text(), server_default=sa.text("''"), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=True,
        ),
    )


def upgrade() -> None:
    # Offline / --sql cannot use connection inspection (MockConnection).
    if alembic_context.is_offline_mode():
        _create_applications_table()
        return
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if insp.has_table("applications"):
        return
    _create_applications_table()


def downgrade() -> None:
    """Drops applications — destructive; use only on disposable databases."""
    op.drop_table("applications")
