"""Optional Postgres ENUM support: ensure empty job_state writes become NULL."""


def test_job_state_cell_writes_null_for_empty_postgres(monkeypatch):
    monkeypatch.setenv("TRACKER_USE_DB", "1")
    monkeypatch.setenv("TRACKER_DATABASE_URL", "postgresql://u:p@localhost:5432/x")
    # Ensure _use_postgres() sees Postgres even if DATABASE_URL is set in the environment.
    monkeypatch.setenv("DATABASE_URL", "")

    from services import tracker_db as tdb

    assert tdb._cell({"job_state": ""}, "job_state") is None
    assert tdb._cell({"job_state": "   "}, "job_state") is None
    assert tdb._cell({"job_state": "skip"}, "job_state") == "skip"


def test_job_state_cell_writes_empty_string_for_sqlite(monkeypatch):
    monkeypatch.setenv("TRACKER_USE_DB", "0")
    monkeypatch.delenv("TRACKER_DATABASE_URL", raising=False)

    from services import tracker_db as tdb

    assert tdb._cell({"job_state": ""}, "job_state") == ""
    assert tdb._cell({"job_state": "   "}, "job_state") == ""

