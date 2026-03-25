"""
applications.job_state — optional Postgres ENUM type (contract v0.1).

This migration is optional (Phase 5). SQLite tracker remains string-based.

We convert empty/invalid values (including legacy '') to NULL so the ENUM
type can be applied without introducing '' as a label.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context as alembic_context
from alembic import op
from sqlalchemy import text

revision: str = "tracker_0010"
down_revision: Union[str, None] = "tracker_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ENUM_NAME = "job_state_enum_v1"
ALLOWED = ("skip", "manual_review", "manual_assist", "safe_auto_apply", "blocked")


def upgrade() -> None:
    if alembic_context.is_offline_mode():
        # Offline migrations can't inspect data; treat as no-op.
        return

    conn = op.get_bind()

    r = conn.execute(
        text(
            """
            SELECT udt_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'applications'
              AND column_name = 'job_state'
            """
        )
    ).fetchone()
    if r and str(r[0]).lower() == ENUM_NAME:
        return

    # Create enum type if missing.
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_type WHERE typname = '{ENUM_NAME}'
                ) THEN
                    CREATE TYPE {ENUM_NAME} AS ENUM ({', '.join(repr(x) for x in ALLOWED)});
                END IF;
            END $$;
            """
        )
    )

    allowed_sql = ", ".join(repr(x) for x in ALLOWED)
    # Normalize existing invalid/legacy values (including '') -> NULL.
    op.execute(
        text(
            f"""
            UPDATE applications
            SET job_state = NULL
            WHERE job_state IS NULL
               OR btrim(job_state) = ''
               OR lower(job_state) NOT IN ({allowed_sql});
            """
        )
    )

    # Apply the enum type as NULLable.
    op.execute(text("ALTER TABLE applications ALTER COLUMN job_state DROP DEFAULT"))
    op.execute(text("ALTER TABLE applications ALTER COLUMN job_state DROP NOT NULL"))
    op.execute(
        text(
            f"""
            ALTER TABLE applications
            ALTER COLUMN job_state
            TYPE {ENUM_NAME}
            USING NULLIF(btrim(job_state), '')::{ENUM_NAME};
            """
        )
    )


def downgrade() -> None:
    if alembic_context.is_offline_mode():
        return

    conn = op.get_bind()
    r = conn.execute(
        text(
            """
            SELECT udt_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'applications'
              AND column_name = 'job_state'
            """
        )
    ).fetchone()
    if not r or str(r[0]).lower() != ENUM_NAME:
        return

    # Convert back to TEXT with legacy default '' and NOT NULL.
    op.execute(
        text(
            """
            ALTER TABLE applications
            ALTER COLUMN job_state
            TYPE TEXT
            USING COALESCE(job_state::text, '');
            """
        )
    )
    op.execute(text("ALTER TABLE applications ALTER COLUMN job_state SET DEFAULT ''"))
    op.execute(text("ALTER TABLE applications ALTER COLUMN job_state SET NOT NULL"))

    # Drop enum type.
    op.execute(text(f"DROP TYPE IF EXISTS {ENUM_NAME}"))

