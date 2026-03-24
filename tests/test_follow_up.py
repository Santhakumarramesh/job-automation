"""Phase 12 — follow-up queue (tracker columns + service)."""

import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


def test_follow_up_priority_sorts_by_ats():
    from services.follow_up_service import list_follow_ups

    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "job_applications.csv"
        import services.application_tracker as at

        orig = at.APPLICATION_FILE
        at.APPLICATION_FILE = csv_path
        os.environ["TRACKER_USE_DB"] = "0"
        try:
            at.initialize_tracker()
            past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
            at.log_application(
                {
                    "target_company": "LowATS",
                    "target_position": "A",
                    "job_id": "low",
                    "user_id": "u1",
                    "fit_decision": "apply",
                    "final_ats_score": "60",
                }
            )
            at.log_application(
                {
                    "target_company": "HighATS",
                    "target_position": "B",
                    "job_id": "high",
                    "user_id": "u1",
                    "fit_decision": "apply",
                    "final_ats_score": "95",
                }
            )
            df = at.load_applications(for_user_id=None)
            for jid, company in (("low", "LowATS"), ("high", "HighATS")):
                rid = str(df[df["job_id"].astype(str) == jid].iloc[0]["id"])
                assert at.update_follow_up_for_row(
                    rid,
                    "u1",
                    {"follow_up_at": past, "follow_up_status": "pending"},
                )
            due = list_follow_ups("u1", due_only=True, limit=10, sort_by_priority=True)
            assert len(due) == 2
            assert due[0]["company"] == "HighATS"
            assert due[0]["follow_up_priority_score"] >= due[1]["follow_up_priority_score"]
        finally:
            at.APPLICATION_FILE = orig
            os.environ.pop("TRACKER_USE_DB", None)


def test_format_follow_up_digest():
    from services.follow_up_service import format_follow_up_digest

    empty = format_follow_up_digest([])
    assert "No due follow-ups" in empty
    one = format_follow_up_digest(
        [
            {
                "company": "Acme",
                "position": "Engineer",
                "follow_up_at": "2026-01-01T12:00:00+00:00",
                "follow_up_note": "Ping recruiter",
                "job_url": "https://example.com/j",
                "follow_up_priority_score": 88.0,
            }
        ]
    )
    assert "Acme" in one and "Engineer" in one and "Ping recruiter" in one


def test_list_follow_ups_due():
    from services.follow_up_service import list_follow_ups

    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "job_applications.csv"
        import services.application_tracker as at

        orig = at.APPLICATION_FILE
        at.APPLICATION_FILE = csv_path
        os.environ["TRACKER_USE_DB"] = "0"
        try:
            at.initialize_tracker()
            past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
            future = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
            at.log_application(
                {
                    "target_company": "A",
                    "target_position": "X",
                    "job_id": "j1",
                    "user_id": "u1",
                }
            )
            at.log_application(
                {
                    "target_company": "FutureCo",
                    "target_position": "Y",
                    "job_id": "j2",
                    "user_id": "u1",
                }
            )
            df = at.load_applications(for_user_id=None)
            rid_past = str(df[df["job_id"].astype(str) == "j1"].iloc[0]["id"])
            rid_future = str(df[df["job_id"].astype(str) == "j2"].iloc[0]["id"])
            assert at.update_follow_up_for_row(
                rid_past,
                "u1",
                {"follow_up_at": past, "follow_up_status": "pending", "follow_up_note": "nudge"},
            )
            assert at.update_follow_up_for_row(
                rid_future,
                "u1",
                {"follow_up_at": future, "follow_up_status": "pending"},
            )
            due = list_follow_ups("u1", due_only=True, limit=10)
            assert len(due) == 1
            assert due[0]["company"] == "A"
        finally:
            at.APPLICATION_FILE = orig
            os.environ.pop("TRACKER_USE_DB", None)


def test_patch_wrong_user_denied():
    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "job_applications.csv"
        import services.application_tracker as at

        orig = at.APPLICATION_FILE
        at.APPLICATION_FILE = csv_path
        os.environ["TRACKER_USE_DB"] = "0"
        try:
            at.initialize_tracker()
            at.log_application(
                {"target_company": "B", "target_position": "Y", "job_id": "j2", "user_id": "alice"}
            )
            df = at.load_applications(for_user_id=None)
            rid = str(df.iloc[0]["id"])
            ok = at.update_follow_up_for_row(
                rid,
                "bob",
                {"follow_up_note": "x"},
            )
            assert ok is False
        finally:
            at.APPLICATION_FILE = orig
            os.environ.pop("TRACKER_USE_DB", None)


try:
    from app.main import app as _follow_up_app  # noqa: F401

    _FOLLOW_UP_APP_OK = True
except ImportError:
    _FOLLOW_UP_APP_OK = False


@pytest.mark.skipif(not _FOLLOW_UP_APP_OK, reason="app.main not available")
def test_follow_up_api_patch():
    import os
    import tempfile
    from pathlib import Path

    import services.application_tracker as at
    from app.auth import User, get_current_user
    from app.main import app
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "job_applications.csv"
        prev = at.APPLICATION_FILE
        prev_db = os.environ.get("TRACKER_USE_DB")
        os.environ["TRACKER_USE_DB"] = "0"
        at.APPLICATION_FILE = csv_path
        try:
            at.initialize_tracker()
            at.log_application(
                {
                    "target_company": "Co",
                    "target_position": "Dev",
                    "job_id": "j-api",
                    "user_id": "alice",
                }
            )
            df = at.load_applications(for_user_id=None)
            rid = str(df.iloc[0]["id"])
            app.dependency_overrides[get_current_user] = lambda: User("alice", [])
            c = TestClient(app)
            r = c.patch(
                f"/api/applications/{rid}/follow-up",
                json={
                    "follow_up_at": "2099-01-01T12:00:00+00:00",
                    "follow_up_status": "pending",
                    "follow_up_note": "email recruiter",
                },
            )
            assert r.status_code == 200, r.text
            g = c.get("/api/follow-ups?due_only=false")
            assert g.status_code == 200
            data = g.json()
            assert data["count"] >= 1
        finally:
            at.APPLICATION_FILE = prev
            app.dependency_overrides.clear()
            if prev_db is None:
                os.environ.pop("TRACKER_USE_DB", None)
            else:
                os.environ["TRACKER_USE_DB"] = prev_db


def test_artifact_metadata_includes_follow_up_when_set():
    from services.artifact_metadata import build_artifact_metadata

    row = {
        "resume_path": "/r.pdf",
        "follow_up_at": "2026-01-01T00:00:00Z",
        "follow_up_status": "pending",
    }
    meta = build_artifact_metadata(row)
    assert "follow_up" in meta
    assert meta["follow_up"]["follow_up_status"] == "pending"
