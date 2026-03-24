"""
Policy service. Central place that decides apply_mode for each job.
Values: auto_easy_apply, manual_assist, skip.

Each decision includes a stable machine-readable policy_reason for audit/debug.
"""

import os
from typing import Any, Dict, List, Optional, Tuple

FIT_THRESHOLD_AUTO_APPLY = 85

# Stable codes for audit logs, tracker.policy_reason, MCP responses
REASON_SKIP_FIT = "skip_fit_decision_not_apply"
REASON_SKIP_UNSUPPORTED = "skip_unsupported_requirements"
REASON_SKIP_ATS = "skip_ats_below_threshold"
REASON_MANUAL_NON_LINKEDIN = "manual_assist_non_linkedin_url"
REASON_MANUAL_EASY_APPLY_UNCONFIRMED = "manual_assist_easy_apply_not_confirmed"
REASON_MANUAL_PROFILE_INCOMPLETE = "manual_assist_profile_incomplete_for_auto"
REASON_MANUAL_ANSWERER_REVIEW = "manual_assist_answerer_manual_review_required"
REASON_AUTO_OK = "auto_easy_apply_all_checks_passed"


def _answerer_review_blocks_auto(answerer_review: Optional[dict]) -> bool:
    """True if any structured answerer field requires manual confirmation."""
    if not answerer_review or not isinstance(answerer_review, dict):
        return False
    return any(
        isinstance(v, dict) and bool(v.get("manual_review_required")) for v in answerer_review.values()
    )


def _job_answerer_blocks_auto(job: dict) -> bool:
    if bool(job.get("answerer_manual_review_required")):
        return True
    ar = job.get("answerer_review")
    if isinstance(ar, str) and ar.strip():
        try:
            import json

            ar = json.loads(ar)
        except Exception:
            return False
    return _answerer_review_blocks_auto(ar if isinstance(ar, dict) else None)


def decide_apply_mode_with_reason(
    job: dict,
    fit_decision: str = "",
    ats_score: int | None = None,
    unsupported_requirements: list | None = None,
    profile_ready: Optional[bool] = None,
    profile: Optional[dict] = None,
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

    from services.job_location_match import check_job_location_policy

    loc_action, loc_reason = check_job_location_policy(job, profile)
    if loc_action == "skip":
        return "skip", loc_reason
    if loc_action == "manual_assist":
        return "manual_assist", loc_reason

    url = str(job.get("url") or job.get("apply_url") or job.get("applyUrl") or "")
    if "linkedin.com" not in url.lower():
        return "manual_assist", REASON_MANUAL_NON_LINKEDIN

    if not job.get("easy_apply_confirmed", False):
        return "manual_assist", REASON_MANUAL_EASY_APPLY_UNCONFIRMED

    if profile_ready is False:
        return "manual_assist", REASON_MANUAL_PROFILE_INCOMPLETE

    if _job_answerer_blocks_auto(job):
        return "manual_assist", REASON_MANUAL_ANSWERER_REVIEW

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
    prof = load_profile()
    desc = str(job.get("description") or job.get("job_description") or "")
    job_policy = {
        "url": job.get("url") or job.get("job_url", ""),
        "apply_url": job.get("apply_url") or job.get("url") or "",
        "easy_apply_confirmed": bool(job.get("easy_apply_confirmed", False)),
        "location": job.get("location") or job.get("locationName") or job.get("job_location") or "",
        "title": job.get("title") or job.get("position") or "",
        "work_type": job.get("work_type") or "",
        "description": desc[:800] if desc else "",
        "answerer_manual_review_required": bool(job.get("answerer_manual_review_required", False)),
        "answerer_review": job.get("answerer_review"),
    }
    return decide_apply_mode_with_reason(
        job_policy,
        fit_decision=str(job.get("fit_decision", "") or ""),
        ats_score=ats_val,
        unsupported_requirements=unsup,
        profile_ready=is_auto_apply_ready(prof),
        profile=prof,
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
    When ``POLICY_ENFORCE_JOB_LOCATION=1``, loads profile for optional location gate.
    """
    prof: Optional[dict] = None
    if os.getenv("POLICY_ENFORCE_JOB_LOCATION", "").lower() in ("1", "true", "yes"):
        try:
            from services.profile_service import load_profile

            prof = load_profile()
        except Exception:
            prof = None
    mode, _ = decide_apply_mode_with_reason(
        job, fit_decision, ats_score, unsupported_requirements, profile_ready, profile=prof
    )
    return mode
