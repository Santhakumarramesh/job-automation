"""Phase 13 / 43 — application insights and answerer_review rollups."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from services.application_insights import (
    compute_answerer_review_insights,
    compute_tracker_insights,
)


def test_compute_answerer_review_insights_from_qa_audit():
    qa = {
        "field_a": "x",
        "_answerer_review": {
            "sponsor": {
                "manual_review_required": True,
                "reason_codes": ["missing_sponsorship_or_work_auth"],
                "classified_type": "sponsorship",
            }
        },
    }
    rows = [{"qa_audit": json.dumps(qa), "company": "Co"}]
    out = compute_answerer_review_insights(rows)
    assert out["tracker_rows_with_answerer_review"] == 1
    assert out["tracker_rows_with_manual_review_flag"] == 1
    assert out["reason_code_counts"].get("missing_sponsorship_or_work_auth") == 1
    assert out["classified_type_counts"].get("sponsorship") == 1


def test_tracker_insights_empty():
    import services.application_tracker as at

    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "job_applications.csv"
        orig = at.APPLICATION_FILE
        at.APPLICATION_FILE = csv_path
        os.environ["TRACKER_USE_DB"] = "0"
        try:
            at.initialize_tracker()
            ins = compute_tracker_insights(None)
            assert ins["total"] == 0
            assert ins["suggestions"]
        finally:
            at.APPLICATION_FILE = orig
            os.environ.pop("TRACKER_USE_DB", None)


try:
    from app.main import app as _insights_app  # noqa: F401

    _INSIGHTS_APP_OK = True
except ImportError:
    _INSIGHTS_APP_OK = False


@pytest.mark.skipif(not _INSIGHTS_APP_OK, reason="app.main not available")
def test_insights_api_includes_answerer_block():
    import services.application_tracker as at
    from app.auth import User, get_current_user
    from app.main import app
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "job_applications.csv"
        prev = at.APPLICATION_FILE
        at.APPLICATION_FILE = csv_path
        os.environ["TRACKER_USE_DB"] = "0"
        try:
            at.initialize_tracker()
            at.log_application(
                {
                    "target_company": "Z",
                    "target_position": "P",
                    "job_id": "j1",
                    "user_id": "alice",
                }
            )
            df = at.load_applications(for_user_id=None)
            rid = str(df.iloc[0]["id"])
            # Patch qa_audit on CSV row — log doesn't set qa; update via pandas
            df2 = at.load_applications(for_user_id=None)
            qa = json.dumps({"_answerer_review": {"q": {"manual_review_required": True, "reason_codes": ["a"], "classified_type": "generic"}}})
            df2.loc[df2["id"].astype(str) == rid, "qa_audit"] = qa
            df2.to_csv(csv_path, index=False)

            app.dependency_overrides[get_current_user] = lambda: User("alice", [])
            c = TestClient(app)
            r = c.get("/api/insights?include_audit=false")
            assert r.status_code == 200, r.text
            data = r.json()
            assert "answerer_review" in data
            assert data["answerer_review"].get("tracker_rows_with_answerer_review", 0) >= 1
        finally:
            at.APPLICATION_FILE = prev
            app.dependency_overrides.clear()
            os.environ.pop("TRACKER_USE_DB", None)
