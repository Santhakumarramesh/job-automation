"""tracker_analytics — Phase 4 admin rollups."""

import pandas as pd

from services.application_tracker import TRACKER_COLUMNS
from services.tracker_analytics import build_admin_tracker_analytics_summary


def test_empty_summary():
    out = build_admin_tracker_analytics_summary(pd.DataFrame())
    assert out["row_count"] == 0
    assert out["by_status"] == {}
    assert out["applied_row_count"] == 0
    assert out["by_applied_iso_week"] == {}
    assert out["rows_with_parseable_applied_at"] == 0


def test_summary_counts_and_applied_breakdown():
    df = pd.DataFrame(
        [
            {
                **{c: "" for c in TRACKER_COLUMNS},
                "status": "Applied",
                "submission_status": "Applied",
                "recruiter_response": "positive",
                "user_id": "u1",
                "workspace_id": "ws1",
            },
            {
                **{c: "" for c in TRACKER_COLUMNS},
                "status": "Applied",
                "submission_status": "Applied",
                "recruiter_response": "Pending",
                "user_id": "u1",
                "workspace_id": "ws1",
            },
            {
                **{c: "" for c in TRACKER_COLUMNS},
                "status": "Shadow",
                "submission_status": "Shadow – Would Apply",
                "recruiter_response": "Pending",
                "user_id": "u2",
                "workspace_id": "",
            },
        ]
    )
    out = build_admin_tracker_analytics_summary(df)
    assert out["row_count"] == 3
    assert out["by_status"].get("Applied") == 2
    assert out["by_status"].get("Shadow") == 1
    assert out["unique_user_ids"] == 2
    assert out["unique_workspace_ids"] == 1
    assert out["applied_row_count"] == 2
    assert out["applied_by_recruiter_response"].get("positive") == 1
    assert out["applied_by_recruiter_response"].get("Pending") == 1
    assert "Applied" in out["status_by_recruiter_response"]


def test_by_applied_iso_week_buckets():
    base = {c: "" for c in TRACKER_COLUMNS}
    df = pd.DataFrame(
        [
            {
                **base,
                "status": "Applied",
                "submission_status": "Applied",
                "applied_at": "2024-01-01T12:00:00",
            },
            {
                **base,
                "status": "Shadow",
                "submission_status": "Shadow – Would Apply",
                "applied_at": "2024-01-03T00:00:00",
            },
            {**base, "status": "Applied", "submission_status": "Applied", "applied_at": "not-a-date"},
        ]
    )
    out = build_admin_tracker_analytics_summary(df)
    assert out["rows_with_parseable_applied_at"] == 2
    assert out["by_applied_iso_week"].get("2024-W01") == 2


def test_status_by_recruiter_response_cross_tab():
    df = pd.DataFrame(
        [
            {
                **{c: "" for c in TRACKER_COLUMNS},
                "status": "Interviewing",
                "submission_status": "Applied",
                "recruiter_response": "positive",
            },
            {
                **{c: "" for c in TRACKER_COLUMNS},
                "status": "Interviewing",
                "submission_status": "Applied",
                "recruiter_response": "negative",
            },
        ]
    )
    out = build_admin_tracker_analytics_summary(df)
    iv = out["status_by_recruiter_response"].get("Interviewing", {})
    assert iv.get("positive") == 1
    assert iv.get("negative") == 1
