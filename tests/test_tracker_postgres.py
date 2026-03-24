"""
Postgres tracker: run only when TEST_POSTGRES_URL is set.
Example: TEST_POSTGRES_URL=postgresql://user:pass@localhost:5432/testdb pytest tests/test_tracker_postgres.py -v
"""

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

PG_URL = os.getenv("TEST_POSTGRES_URL", "").strip()
_REPO_ROOT = Path(__file__).resolve().parent.parent


def _has_alembic() -> bool:
    try:
        import alembic  # noqa: F401

        return True
    except ImportError:
        return False


@pytest.mark.skipif(not PG_URL or not _has_alembic(), reason="TEST_POSTGRES_URL or alembic not available")
def test_alembic_baseline_upgrade():
    """Phase 3.2.2 — migrations apply on a real Postgres URL."""
    env = {**os.environ, "TRACKER_DATABASE_URL": PG_URL}
    env.pop("DATABASE_URL", None)
    r = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr or r.stdout


@pytest.mark.skipif(not PG_URL, reason="TEST_POSTGRES_URL not set")
def test_tracker_postgres_roundtrip():
    try:
        import psycopg2  # noqa: F401
    except ImportError:
        pytest.skip("psycopg2 not installed (pip install .[postgres])")

    prev_use = os.environ.get("TRACKER_USE_DB")
    prev_t = os.environ.get("TRACKER_DATABASE_URL")
    prev_d = os.environ.get("DATABASE_URL")
    os.environ["TRACKER_USE_DB"] = "1"
    os.environ["TRACKER_DATABASE_URL"] = PG_URL
    os.environ.pop("DATABASE_URL", None)

    try:
        from services import tracker_db as tdb

        tdb.close_tracker_pg_pool()
        jid = f"pg-test-{uuid.uuid4().hex[:8]}"
        tdb.initialize_tracker_db()
        rid = tdb.log_application_db(
            {
                "source": "pytest",
                "job_id": jid,
                "company": "TestCo",
                "position": "Engineer",
                "user_id": "pg-test-user",
                "policy_reason": "test",
            }
        )
        assert rid
        df = tdb.load_applications_db()
        assert (df["job_id"] == jid).any()
    finally:
        try:
            from services import tracker_db as tdb
            tdb.close_tracker_pg_pool()
        except Exception:
            pass
        if prev_use is not None:
            os.environ["TRACKER_USE_DB"] = prev_use
        else:
            os.environ.pop("TRACKER_USE_DB", None)
        if prev_t is not None:
            os.environ["TRACKER_DATABASE_URL"] = prev_t
        else:
            os.environ.pop("TRACKER_DATABASE_URL", None)
        if prev_d is not None:
            os.environ["DATABASE_URL"] = prev_d
