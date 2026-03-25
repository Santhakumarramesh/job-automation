from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_tracker_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Keep tracker state isolated per test run.

    Some tests assert exact row counts and can bleed through shared local
    `job_applications.db` / CSV files when environment defaults leak in.
    """
    db_path = tmp_path / "job_applications.db"
    csv_path = tmp_path / "job_applications.csv"

    # Prefer isolated SQLite tracker paths for tests.
    monkeypatch.setenv("TRACKER_USE_DB", "1")
    monkeypatch.setenv("TRACKER_DB_PATH", str(db_path))
    monkeypatch.delenv("TRACKER_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    # Keep module-level globals aligned with isolated paths.
    from services import application_tracker, tracker_db

    tracker_db.close_tracker_pg_pool()
    application_tracker.APPLICATION_FILE = csv_path
    application_tracker.USE_DB = True

    yield

    tracker_db.close_tracker_pg_pool()
