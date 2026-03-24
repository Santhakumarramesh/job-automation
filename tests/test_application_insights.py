"""Phase 13 / 43 — application insights and answerer_review rollups."""

import json
import os
import tempfile
from pathlib import Path

import pytest

import pandas as pd

from services.application_insights import (
    _failure_hint_from_crosstabs,
    compute_answerer_review_insights,
    compute_pipeline_correlations,
    compute_tracker_crosstabs,
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


def test_compute_pipeline_correlations_offer_accepted():
    df = pd.DataFrame(
        [
            {"policy_reason": "auto_easy_apply", "offer_outcome": "accepted", "interview_stage": ""},
            {"policy_reason": "auto_easy_apply", "offer_outcome": "Accepted", "interview_stage": "completed"},
            {"policy_reason": "manual_assist", "offer_outcome": "declined", "interview_stage": ""},
        ]
    )
    pc = compute_pipeline_correlations(df)
    acc = pc["policy_reason_when_offer_accepted"]
    assert acc.get("auto_easy_apply") == 2
    dec = pc["policy_reason_when_offer_declined"]
    assert dec.get("manual_assist") == 1


def test_compute_tracker_crosstabs_pairs():
    df = pd.DataFrame(
        [
            {"submission_status": "Failed – X", "policy_reason": "p1", "apply_mode": "auto_easy_apply"},
            {"submission_status": "Failed – X", "policy_reason": "p1", "apply_mode": "auto_easy_apply"},
            {"submission_status": "Applied", "policy_reason": "p2", "apply_mode": "manual_assist"},
        ]
    )
    xt = compute_tracker_crosstabs(df)
    sp = xt["submission_status_by_policy_reason"]
    assert any(r["count"] == 2 for r in sp)
    assert sp[0]["count"] >= 2


def test_failure_hint_from_crosstabs_clusters():
    xt = {
        "submission_status_by_policy_reason": [
            {"submission_status": "Failed – Form", "policy_reason": "manual_assist", "count": 4},
            {"submission_status": "Failed – Form", "policy_reason": "skip_fit", "count": 1},
        ]
    }
    h = _failure_hint_from_crosstabs(xt)
    assert h is not None
    assert "manual_assist" in h


def test_tracker_insights_includes_pipeline(monkeypatch):
    df = pd.DataFrame(
        [
            {
                "submission_status": "Applied",
                "apply_mode": "auto_easy_apply",
                "policy_reason": "auto_easy_apply",
                "fit_decision": "apply",
                "recruiter_response": "Pending",
                "interview_stage": "scheduled",
                "offer_outcome": "none",
                "ats_score": "80",
            }
        ]
    )

    def fake_load(for_user_id=None):
        return df

    monkeypatch.setattr("services.application_tracker.load_applications", fake_load)
    ins = compute_tracker_insights("any")
    assert ins["total"] == 1
    assert ins["by_interview_stage"].get("scheduled") == 1
    assert "pipeline_correlations" in ins


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
            assert ins["by_interview_stage"] == {}
            assert ins["by_offer_outcome"] == {}
            assert "pipeline_correlations" in ins
            assert "crosstabs" in ins
            assert ins["crosstabs"]["submission_status_by_policy_reason"] == []
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
            assert "crosstabs" in (data.get("tracker") or {})
        finally:
            at.APPLICATION_FILE = prev
            app.dependency_overrides.clear()
            os.environ.pop("TRACKER_USE_DB", None)
