"""
Operator helper: incident triage for apply-runner SLOs (Phase 8).

This script reads the current apply-runner Redis metrics hash via
`services.apply_runner_metrics_redis.read_apply_runner_metrics_summary()`,
computes SLO-relevant averages/ratios, and prints which Phase 7.4 alert(s)
and Phase 7.4 playbook section(s) to follow.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        if v is None:
            return default
        return int(float(v))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class SloInputs:
    avg_fill_total_seconds: Optional[float]
    avg_dom_scan_seconds: Optional[float]
    avg_unmapped_fields: Optional[float]
    blocked_share: Optional[float]

    timeouts_total: Optional[int]
    timeouts_in_15m: Optional[int]


def compute_slo_inputs(fields: Dict[str, str], *, timeouts_in_15m: Optional[int] = None) -> SloInputs:
    def avg_sum_count(sum_key: str, count_key: str) -> Optional[float]:
        s = _safe_float(fields.get(sum_key))
        c = _safe_int(fields.get(count_key))
        if c <= 0:
            return None
        return s / float(c)

    avg_fill_total_seconds = avg_sum_count(
        "linkedin_fill_total_seconds_sum",
        "linkedin_fill_total_seconds_count",
    )
    avg_dom_scan_seconds = avg_sum_count(
        "linkedin_fill_dom_scan_seconds_sum",
        "linkedin_fill_dom_scan_seconds_count",
    )
    avg_unmapped_fields = avg_sum_count(
        "linkedin_fill_unmapped_fields_sum",
        "linkedin_fill_unmapped_fields_count",
    )

    attempt_total = _safe_int(fields.get("linkedin_live_submit_attempt_total"))
    blocked_total = _safe_int(fields.get("linkedin_live_submit_blocked_autonomy_total"))
    if attempt_total <= 0:
        blocked_share = None
    else:
        blocked_share = blocked_total / float(attempt_total)

    timeouts_total = _safe_int(fields.get("linkedin_fill_playwright_timeout_total"))

    return SloInputs(
        avg_fill_total_seconds=avg_fill_total_seconds,
        avg_dom_scan_seconds=avg_dom_scan_seconds,
        avg_unmapped_fields=avg_unmapped_fields,
        blocked_share=blocked_share,
        timeouts_total=timeouts_total,
        timeouts_in_15m=timeouts_in_15m,
    )


def _prometheus_query_increase(prom_base: str, prom_expr: str) -> Optional[float]:
    """
    Query Prometheus `/api/v1/query` and return the numeric result.

    This is optional; use when you want time-window SLOs like "increase(...[15m])".
    """
    import json
    from urllib.parse import urlencode
    from urllib.request import urlopen, Request

    if not prom_base:
        return None
    base = prom_base.rstrip("/")
    url = f"{base}/api/v1/query"
    params = urlencode({"query": prom_expr})

    req = Request(url + "?" + params, headers={"Accept": "application/json"})
    with urlopen(req, timeout=8) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        if data.get("status") != "success":
            return None
        res = (data.get("data") or {}).get("result") or []
        if not res:
            return None
        # { "value": [ <ts>, "<string>" ] }
        val = (res[0] or {}).get("value") or []
        if len(val) >= 2:
            return _safe_float(val[1], default=0.0)
        return None


def triage(fields: Dict[str, str], *, timeouts_in_15m: Optional[int] = None) -> Dict[str, Any]:
    inputs = compute_slo_inputs(fields, timeouts_in_15m=timeouts_in_15m)

    # Phase 7.4 alert thresholds (approximate):
    # - Avg fill latency alert when > 240s
    # - DOM scan alert when > 40s
    # - Unmapped fields alert when > 8 avg per run
    # - Truth gate blocked alert when blocked share > 0.25
    # - Playwright timeout spike when increase(...) >= 3 over 15m
    fired = []

    if inputs.avg_fill_total_seconds is not None and inputs.avg_fill_total_seconds > 240:
        fired.append("ApplyRunnerAvgFillLatencyHigh")
    if inputs.avg_dom_scan_seconds is not None and inputs.avg_dom_scan_seconds > 40:
        fired.append("ApplyRunnerAvgDomScanHigh")
    if inputs.avg_unmapped_fields is not None and inputs.avg_unmapped_fields > 8:
        fired.append("ApplyRunnerAvgUnmappedFieldsHigh")
    if inputs.blocked_share is not None and inputs.blocked_share > 0.25:
        fired.append("TruthGateBlockedShareHigh")
    if inputs.timeouts_in_15m is not None and inputs.timeouts_in_15m >= 3:
        fired.append("ApplyRunnerPlaywrightTimeoutSpike")

    return {"inputs": inputs, "fired": fired}


def main() -> int:
    # Optional: Prometheus time-window support for timeouts SLO.
    prom_base = os.getenv("PROMETHEUS_BASE_URL", "").strip()
    timeouts_in_15m: Optional[int] = None
    if prom_base:
        val = _prometheus_query_increase(
            prom_base,
            "increase(ccp_apply_runner_linkedin_fill_playwright_timeout_total[15m])",
        )
        if val is not None:
            timeouts_in_15m = int(round(val))

    from services.apply_runner_metrics_redis import read_apply_runner_metrics_summary

    snap = read_apply_runner_metrics_summary()
    fields = (snap or {}).get("fields") or {}

    out = triage(fields, timeouts_in_15m=timeouts_in_15m)
    inputs: SloInputs = out["inputs"]
    fired = out["fired"]

    print("=== Apply-runner SLO triage (Phase 8) ===")
    print(f"Enabled (workers publishing): {snap.get('enabled')}")
    print(f"Redis hash: {snap.get('hash')}")
    print("")

    def fmt_opt(x: Optional[float]) -> str:
        if x is None:
            return "n/a"
        return f"{x:.3f}"

    print(f"Avg fill total seconds: {fmt_opt(inputs.avg_fill_total_seconds)}")
    print(f"Avg DOM scan seconds:   {fmt_opt(inputs.avg_dom_scan_seconds)}")
    print(f"Avg unmapped/run:      {fmt_opt(inputs.avg_unmapped_fields)}")
    if inputs.blocked_share is None:
        print("Blocked share:         n/a (no attempts)")
    else:
        print(f"Blocked share:         {inputs.blocked_share:.3f}")

    if inputs.timeouts_in_15m is not None:
        print(f"Playwright timeouts:   {inputs.timeouts_in_15m} over last 15m (Prometheus)")
    else:
        print(f"Playwright timeouts:   {inputs.timeouts_total} total (Redis); 15m window needs PROMETHEUS_BASE_URL")

    print("")
    if fired:
        print("Likely alert(s) / playbook lanes to follow:")
        for a in fired:
            print(f"- {a}")
        print("")
        print("Use these sections in docs/ITPLY_RECOVERY_PLAYBOOKS.md:")
        print("- Metrics-driven triage (Phase 7.4)")
    else:
        print("No Phase 7.4 alert thresholds are currently breached by the computed averages/ratios.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

