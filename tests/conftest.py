from __future__ import annotations

import os
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

    # Keep tracker files isolated, but do not force DB-vs-CSV mode.
    monkeypatch.setenv("TRACKER_DB_PATH", str(db_path))
    monkeypatch.delenv("TRACKER_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    # Keep module-level globals aligned with isolated paths.
    from services import application_tracker, tracker_db

    tracker_db.close_tracker_pg_pool()
    tracker_db.CSV_FILE = csv_path
    application_tracker.APPLICATION_FILE = csv_path
    application_tracker.USE_DB = os.getenv("TRACKER_USE_DB", "").lower() in (
        "1",
        "true",
        "yes",
    )

    yield

    tracker_db.close_tracker_pg_pool()
