"""Tracker row enrichment (ATS + ceiling + address + package stats)."""

from services.tracker_context import build_tracker_row_extras


def test_build_tracker_row_extras_ats_and_ceiling():
    ex = build_tracker_row_extras(
        {
            "job_url": "https://linkedin.com/jobs/view/1",
            "apply_url": "https://boards.greenhouse.io/x/jobs/1",
            "truth_safe_ats_ceiling": 88,
            "selected_address_label": "NYC apartment",
            "package_field_stats": {"auto_filled": 3, "unmapped": 1},
        }
    )
    assert ex["ats_provider"] == "linkedin_jobs"
    assert ex["ats_provider_apply_target"] == "greenhouse"
    assert ex["truth_safe_ats_ceiling"] == "88"
    assert ex["selected_address_label"] == "NYC apartment"
    assert "auto_filled" in ex["package_field_stats"]
