"""
Policy service. Central place that decides apply_mode for each job.
Values: auto_easy_apply, manual_assist, skip.
"""

from typing import Any

FIT_THRESHOLD_AUTO_APPLY = 85


def decide_apply_mode(
    job: dict,
    fit_decision: str = "",
    ats_score: int | None = None,
    unsupported_requirements: list | None = None,
) -> str:
    """
    Decide apply_mode for a job.
    Returns: auto_easy_apply, manual_assist, or skip.
    """
    job = job or {}
    unsup = unsupported_requirements or []

    # Skip: fit says don't apply
    if fit_decision and str(fit_decision).lower() != "apply":
        return "skip"

    # Skip: has unsupported requirements
    if unsup:
        return "skip"

    # Skip: ATS below threshold (when provided)
    if ats_score is not None and int(ats_score) < FIT_THRESHOLD_AUTO_APPLY:
        return "skip"

    # Manual-assist: not LinkedIn Easy Apply
    url = str(job.get("url") or job.get("apply_url") or job.get("applyUrl") or "")
    if "linkedin.com" not in url.lower():
        return "manual_assist"

    # Manual-assist: Easy Apply not confirmed (MCP didn't confirm per-job)
    if not job.get("easy_apply_confirmed", False):
        return "manual_assist"

    return "auto_easy_apply"
