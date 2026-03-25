from __future__ import annotations

from scripts.triage_apply_runner_slo import compute_slo_inputs, triage


def test_compute_slo_inputs_avg_and_blocked_share():
    fields = {
        "linkedin_fill_total_seconds_sum": "600",
        "linkedin_fill_total_seconds_count": "5",
        "linkedin_fill_dom_scan_seconds_sum": "200",
        "linkedin_fill_dom_scan_seconds_count": "5",
        "linkedin_fill_unmapped_fields_sum": "60",
        "linkedin_fill_unmapped_fields_count": "10",
        "linkedin_live_submit_attempt_total": "100",
        "linkedin_live_submit_blocked_autonomy_total": "30",
        "linkedin_fill_playwright_timeout_total": "7",
    }
    inputs = compute_slo_inputs(fields, timeouts_in_15m=None)
    assert inputs.avg_fill_total_seconds == 120.0
    assert inputs.avg_dom_scan_seconds == 40.0
    assert inputs.avg_unmapped_fields == 6.0
    assert inputs.blocked_share == 0.3
    assert inputs.timeouts_total == 7
    assert inputs.timeouts_in_15m is None


def test_triage_fires_expected_alerts_from_thresholds():
    # Trip fill latency (>240), unmapped avg (>8), blocked share (>0.25)
    fields = {
        "linkedin_fill_total_seconds_sum": "1500",
        "linkedin_fill_total_seconds_count": "5",  # 300s avg
        "linkedin_fill_dom_scan_seconds_sum": "500",
        "linkedin_fill_dom_scan_seconds_count": "10",  # 50s avg (does not exceed >40? yes, exceeds)
        "linkedin_fill_unmapped_fields_sum": "90",
        "linkedin_fill_unmapped_fields_count": "10",  # 9 avg (>8)
        "linkedin_live_submit_attempt_total": "80",
        "linkedin_live_submit_blocked_autonomy_total": "30",  # 0.375
        "linkedin_fill_playwright_timeout_total": "1",
    }
    out = triage(fields, timeouts_in_15m=3)
    assert set(out["fired"]) == {
        "ApplyRunnerAvgFillLatencyHigh",
        "ApplyRunnerAvgDomScanHigh",
        "ApplyRunnerAvgUnmappedFieldsHigh",
        "TruthGateBlockedShareHigh",
        "ApplyRunnerPlaywrightTimeoutSpike",
    }

