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
    compute_shadow_insights,
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


def test_compute_shadow_insights_counts():
    df = pd.DataFrame(
        [
            {"submission_status": "Shadow – Would Apply", "status": "Shadow"},
            {"submission_status": "Shadow – Would Not Apply", "status": "Shadow"},
            {"submission_status": "Applied", "status": "Applied"},
            {"submission_status": "Dry Run Complete", "status": "Rejected"},
        ]
    )
    sh = compute_shadow_insights(df)
    assert sh["shadow_rows"] == 2
    assert sh["shadow_would_apply_rows"] == 1
    assert sh["shadow_would_not_apply_rows"] == 1
    assert sh["shadow_decided_total"] == 2
    assert sh["shadow_positive_rate"] == 0.5
    assert sh["shadow_to_applied_ratio"] == 1.0
    assert sh["applied_submission_rows"] == 1
    assert sh["tracker_status_shadow_rows"] == 2
    assert sh["runner_issue_proxy_rows"] == 0
    assert "fp_fn_definitions_v0" in sh
    assert sh["policy_reference"].get("FIT_THRESHOLD_AUTO_APPLY") == 85
    assert sh["closed_loop_hints_v0"] == []


def test_compute_shadow_insights_runner_issue_proxy():
    df = pd.DataFrame(
        [
            {"submission_status": "Failed – checkpoint", "status": "Applied", "qa_audit": "{}"},
            {"submission_status": "Applied", "status": "Applied", "qa_audit": "timeout on page"},
            {"submission_status": "Shadow – Would Apply", "status": "Shadow", "qa_audit": ""},
        ]
    )
    sh = compute_shadow_insights(df)
    assert sh["runner_issue_proxy_rows"] == 2
    assert sh["runner_issue_proxy_rate"] > 0


def test_closed_loop_hints_friction_and_positive_shadow():
    rows = []
    for _ in range(6):
        rows.append({"submission_status": "Shadow – Would Apply", "status": "Shadow", "qa_audit": ""})
    for _ in range(4):
        rows.append({"submission_status": "Shadow – Would Not Apply", "status": "Shadow", "qa_audit": ""})
    for _ in range(3):
        rows.append({"submission_status": "Failed – checkpoint", "status": "Applied", "qa_audit": "{}"})
    df = pd.DataFrame(rows)
    sh = compute_shadow_insights(df)
    assert sh["shadow_decided_total"] == 10
    assert sh["shadow_positive_rate"] >= 0.55
    assert sh["runner_issue_proxy_rate"] >= 0.2
    hints = sh.get("closed_loop_hints_v0") or []
    assert any("friction" in h.lower() or "playwright" in h.lower() for h in hints)


def test_closed_loop_hints_low_shadow_positive():
    rows = []
    for _ in range(8):
        rows.append({"submission_status": "Shadow – Would Not Apply", "status": "Shadow"})
    for _ in range(2):
        rows.append({"submission_status": "Shadow – Would Apply", "status": "Shadow"})
    df = pd.DataFrame(rows)
    sh = compute_shadow_insights(df)
    assert sh["shadow_positive_rate"] <= 0.4
    hints = sh.get("closed_loop_hints_v0") or []
    assert any("would-not-apply" in h.lower() or "strict" in h.lower() for h in hints)


def test_closed_loop_hints_shadow_exceeds_applied():
    rows = []
    for _ in range(5):
        rows.append({"submission_status": "Shadow – Would Apply", "status": "Shadow"})
    rows.append({"submission_status": "Applied", "status": "Applied"})
    df = pd.DataFrame(rows)
    sh = compute_shadow_insights(df)
    assert sh["shadow_to_applied_ratio"] >= 2.5
    hints = sh.get("closed_loop_hints_v0") or []
    assert any("materially exceeds" in h.lower() or "blockers" in h.lower() for h in hints)


def test_compute_tracker_crosstabs_pairs():
    df = pd.DataFrame(
        [
            {"submission_status": "Failed – X", "policy_reason": "p1", "apply_mode": "auto_easy_apply"},
            {"submission_status": "Failed – X", "policy_reason": "p1", "apply_mode": "auto_easy_apply"},
            {"submission_status": "Applied", "policy_reason": "p2", "apply_mode": "manual_assist"},
        ]
    )
    xt = compute_tracker_crosstabs(df)
    assert "apply_mode_by_ats_provider_apply_target" in xt
    assert "submission_status_by_ats_provider_apply_target" in xt
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

    def fake_load(for_user_id=None, workspace_id=None, **kwargs):
        return df

    monkeypatch.setattr("services.application_tracker.load_applications", fake_load)
    ins = compute_tracker_insights("any")
    assert ins["total"] == 1
    assert ins["by_interview_stage"].get("scheduled") == 1
    assert "pipeline_correlations" in ins
    assert "shadow" in ins
    assert ins["shadow"]["shadow_rows"] == 0


def test_tracker_insights_audit_provider_and_ceiling(monkeypatch):
    df = pd.DataFrame(
        [
            {
                "submission_status": "Applied",
                "apply_mode": "auto_easy_apply",
                "policy_reason": "auto_easy_apply",
                "fit_decision": "apply",
                "recruiter_response": "Pending",
                "interview_stage": "",
                "offer_outcome": "",
                "ats_score": "90",
                "ats_provider": "linkedin_jobs",
                "ats_provider_apply_target": "linkedin_jobs",
                "truth_safe_ats_ceiling": "88",
            },
            {
                "submission_status": "Applied",
                "apply_mode": "manual_assist",
                "policy_reason": "manual_assist_external_apply_url",
                "fit_decision": "apply",
                "recruiter_response": "Pending",
                "interview_stage": "",
                "offer_outcome": "",
                "ats_score": "85",
                "ats_provider": "linkedin_jobs",
                "ats_provider_apply_target": "greenhouse",
                "truth_safe_ats_ceiling": "82",
            },
        ]
    )

    def fake_load(for_user_id=None, workspace_id=None, **kwargs):
        return df

    monkeypatch.setattr("services.application_tracker.load_applications", fake_load)
    ins = compute_tracker_insights("any")
    assert ins["by_ats_provider"].get("linkedin_jobs") == 2
    assert ins["by_ats_provider_apply_target"].get("greenhouse") == 1
    tc = ins["truth_safe_ats_ceiling"]
    assert tc["count_numeric"] == 2
    assert tc["mean"] == 85.0


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
            assert ins["by_ats_provider"] == {}
            assert ins["truth_safe_ats_ceiling"]["count_numeric"] == 0
            assert "pipeline_correlations" in ins
            assert "crosstabs" in ins
            assert ins["crosstabs"]["submission_status_by_policy_reason"] == []
            assert ins.get("shadow") is not None
            assert ins["shadow"]["shadow_rows"] == 0
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
            df2 = at.load_applications(for_user_id=None).copy()
            df2["qa_audit"] = df2["qa_audit"].astype(object)
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
