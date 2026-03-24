"""
Policy service. Central place that decides apply_mode for each job.
Values: auto_easy_apply, manual_assist, skip.

Each decision includes a stable machine-readable policy_reason for audit/debug.
"""

from typing import Any, Dict, List, Optional, Tuple

FIT_THRESHOLD_AUTO_APPLY = 85

# Stable codes for audit logs, tracker.policy_reason, MCP responses
REASON_SKIP_FIT = "skip_fit_decision_not_apply"
REASON_SKIP_UNSUPPORTED = "skip_unsupported_requirements"
REASON_SKIP_ATS = "skip_ats_below_threshold"
REASON_MANUAL_NON_LINKEDIN = "manual_assist_non_linkedin_url"
REASON_MANUAL_EASY_APPLY_UNCONFIRMED = "manual_assist_easy_apply_not_confirmed"
REASON_MANUAL_PROFILE_INCOMPLETE = "manual_assist_profile_incomplete_for_auto"
REASON_AUTO_OK = "auto_easy_apply_all_checks_passed"


def decide_apply_mode_with_reason(
    job: dict,
    fit_decision: str = "",
    ats_score: int | None = None,
    unsupported_requirements: list | None = None,
    profile_ready: Optional[bool] = None,
) -> Tuple[str, str]:
    """
    Decide apply_mode and return (mode, policy_reason).

    profile_ready:
      - None: do not gate auto-apply on candidate profile (legacy / discovery-only).
      - True/False: if False, downgrade auto_easy_apply → manual_assist when all else passes.
    """
    job = job or {}
    unsup = unsupported_requirements or []

    if fit_decision and str(fit_decision).lower() != "apply":
        return "skip", REASON_SKIP_FIT

    if unsup:
        return "skip", REASON_SKIP_UNSUPPORTED

    if ats_score is not None and int(ats_score) < FIT_THRESHOLD_AUTO_APPLY:
        return "skip", REASON_SKIP_ATS

    url = str(job.get("url") or job.get("apply_url") or job.get("applyUrl") or "")
    if "linkedin.com" not in url.lower():
        return "manual_assist", REASON_MANUAL_NON_LINKEDIN

    if not job.get("easy_apply_confirmed", False):
        return "manual_assist", REASON_MANUAL_EASY_APPLY_UNCONFIRMED

    if profile_ready is False:
        return "manual_assist", REASON_MANUAL_PROFILE_INCOMPLETE

    return "auto_easy_apply", REASON_AUTO_OK


def policy_from_exported_job(job: Dict[str, Any]) -> Tuple[str, str]:
    """
    Compute (apply_mode, policy_reason) from a job dict (export / JSON / MCP payload).
    Loads profile to gate auto-apply.
    """
    from services.profile_service import load_profile, is_auto_apply_ready

    job = job or {}
    ats_raw = job.get("ats_score", job.get("final_ats_score"))
    ats_val: Optional[int] = None
    if ats_raw is not None and str(ats_raw).strip() != "":
        try:
            ats_val = int(float(ats_raw))
        except (TypeError, ValueError):
            ats_val = None
    unsup: List = job.get("unsupported_requirements") or []
    if isinstance(unsup, str):
        try:
            import json
            unsup = json.loads(unsup)
        except Exception:
            unsup = []
    if not isinstance(unsup, list):
        unsup = []
    job_policy = {
        "url": job.get("url") or job.get("job_url", ""),
        "apply_url": job.get("apply_url") or job.get("url") or "",
        "easy_apply_confirmed": bool(job.get("easy_apply_confirmed", False)),
    }
    return decide_apply_mode_with_reason(
        job_policy,
        fit_decision=str(job.get("fit_decision", "") or ""),
        ats_score=ats_val,
        unsupported_requirements=unsup,
        profile_ready=is_auto_apply_ready(load_profile()),
    )


def decide_apply_mode(
    job: dict,
    fit_decision: str = "",
    ats_score: int | None = None,
    unsupported_requirements: list | None = None,
    profile_ready: Optional[bool] = None,
) -> str:
    """
    Decide apply_mode for a job.
    Returns: auto_easy_apply, manual_assist, or skip.
    """
    mode, _ = decide_apply_mode_with_reason(
        job, fit_decision, ats_score, unsupported_requirements, profile_ready
    )
    return mode
