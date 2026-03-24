"""Phase 4.2.1 — database-backed job idempotency."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest


def test_can_use_db_postgres_requires_tracker_use_db():
    from services.idempotency_db import can_use_db_for_idempotency, idempotency_db_requested

    with patch.dict(
        os.environ,
        {
            "IDEMPOTENCY_USE_DB": "1",
            "DATABASE_URL": "postgresql://u:p@localhost:5432/db",
            "TRACKER_USE_DB": "0",
        },
        clear=False,
    ):
        assert idempotency_db_requested() is True
        assert can_use_db_for_idempotency() is False


def test_resolve_enqueue_sqlite_second_call_skips_enqueue():
    pytest.importorskip("celery")
    import app.tasks as tasks_mod

    with TemporaryDirectory() as td:
        dbfile = Path(td) / "idem.db"
        url = f"sqlite:///{dbfile.resolve().as_posix()}"
        env = {
            "DATABASE_URL": url,
            "IDEMPOTENCY_USE_DB": "1",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch.object(tasks_mod.run_job, "apply_async") as m:
                j1 = tasks_mod.enqueue_job("n", {}, "u1", idempotency_key="idem-a")
                j2 = tasks_mod.enqueue_job("n", {}, "u1", idempotency_key="idem-a")
            assert j1 == j2
            assert m.call_count == 1


def test_resolve_idempotent_enqueue_sqlite_returns_same_id():
    with TemporaryDirectory() as td:
        dbfile = Path(td) / "x.db"
        url = f"sqlite:///{dbfile.resolve().as_posix()}"
        with patch.dict(os.environ, {"DATABASE_URL": url, "IDEMPOTENCY_USE_DB": "1"}, clear=False):
            from services.idempotency_keys import resolve_idempotent_enqueue

            a1, e1 = resolve_idempotent_enqueue("alice", "k1")
            assert e1 is True
            a2, e2 = resolve_idempotent_enqueue("alice", "k1")
            assert e2 is False
            assert a1 == a2


def test_startup_warns_when_idempotency_db_unavailable():
    from services.startup_checks import collect_startup_report

    with patch.dict(
        os.environ,
        {
            "IDEMPOTENCY_USE_DB": "1",
            "DATABASE_URL": "postgresql://x:y@h:5432/db",
            "TRACKER_USE_DB": "0",
            "APP_ENV": "development",
            "STRICT_STARTUP": "0",
        },
        clear=False,
    ):
        _, warnings = collect_startup_report("app")
    assert any("IDEMPOTENCY_USE_DB=1" in w and "inactive" in w for w in warnings)
