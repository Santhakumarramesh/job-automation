"""applications.application_decision as JSONB (Postgres queryable JSON)

Revision ID: tracker_0009
Revises: tracker_0008
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context as alembic_context
from alembic import op
from sqlalchemy import text

revision: str = "tracker_0009"
down_revision: Union[str, None] = "tracker_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if alembic_context.is_offline_mode():
        op.execute(
            sa.text(
                """
                ALTER TABLE applications
                ALTER COLUMN application_decision
                TYPE jsonb
                USING (
                  CASE
                    WHEN application_decision IS NULL OR btrim(application_decision::text) = ''
                    THEN NULL::jsonb
                    ELSE application_decision::jsonb
                  END
                )
                """
            )
        )
        return
    conn = op.get_bind()
    r = conn.execute(
        text(
            """
            SELECT udt_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'applications'
              AND column_name = 'application_decision'
            """
        )
    )
    row = r.fetchone()
    if not row:
        return
    if str(row[0]).lower() == "jsonb":
        return
    op.execute(text("ALTER TABLE applications ALTER COLUMN application_decision DROP DEFAULT"))
    op.execute(
        text(
            """
            ALTER TABLE applications
            ALTER COLUMN application_decision
            TYPE jsonb
            USING (
              CASE
                WHEN application_decision IS NULL OR btrim(application_decision::text) = ''
                THEN NULL::jsonb
                ELSE application_decision::jsonb
              END
            )
            """
        )
    )


def downgrade() -> None:
    if alembic_context.is_offline_mode():
        op.execute(
            sa.text(
                "ALTER TABLE applications ALTER COLUMN application_decision TYPE text "
                "USING COALESCE(application_decision::text, '')"
            )
        )
        return
    conn = op.get_bind()
    r = conn.execute(
        text(
            """
            SELECT udt_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'applications'
              AND column_name = 'application_decision'
            """
        )
    )
    row = r.fetchone()
    if not row or str(row[0]).lower() != "jsonb":
        return
    op.execute(text("ALTER TABLE applications ALTER COLUMN application_decision DROP DEFAULT"))
    op.execute(
        text(
            "ALTER TABLE applications ALTER COLUMN application_decision TYPE text "
            "USING COALESCE(application_decision::text, '')"
        )
    )
