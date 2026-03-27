"""
Phase 10 — Runner guardrails for the approved queue executor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from services.apply_queue_service import JobQueueState


@dataclass
class RunnerValidation:
    ok: bool
    error: str = ""


@dataclass
class RunnerOutcome:
    runner_state: str
    job_state: Optional[str] = None
    error: str = ""


def validate_queue_item(item: dict) -> RunnerValidation:
    job_url = str(item.get("job_url") or item.get("url") or "").strip()
    job_title = str(item.get("job_title") or item.get("title") or "").strip()
    company = str(item.get("company") or "").strip()
    if not job_url:
        return RunnerValidation(False, "missing_job_url")
    if "linkedin.com" not in job_url.lower():
        return RunnerValidation(False, "unsupported_apply_target")
    if not job_title or not company:
        return RunnerValidation(False, "missing_job_metadata")
    if str(item.get("job_state") or "") != JobQueueState.APPROVED_FOR_APPLY:
        return RunnerValidation(False, "job_not_approved")
    return RunnerValidation(True, "")


def _retryable_message(msg: str) -> bool:
    m = (msg or "").lower()
    return any(k in m for k in ["login", "challenge", "checkpoint", "verification required"])


def classify_apply_payload(payload: dict) -> RunnerOutcome:
    if not payload or payload.get("status") != "ok":
        message = payload.get("message", "apply_failed") if isinstance(payload, dict) else "apply_failed"
        if _retryable_message(message):
            return RunnerOutcome("retry_needed", JobQueueState.APPROVED_FOR_APPLY, message)
        return RunnerOutcome("failed", JobQueueState.BLOCKED, message)

    results = payload.get("results") or []
    if not results:
        return RunnerOutcome("failed", JobQueueState.BLOCKED, "empty_results")

    r0 = results[0] or {}
    status = str(r0.get("status") or "").strip()
    err = str(r0.get("error") or "").strip()

    if status == "applied":
        return RunnerOutcome("submitted", JobQueueState.APPLIED, "")
    if status in ("manual_assist_ready", "shadow_would_not_apply"):
        return RunnerOutcome("stopped_review_required", JobQueueState.REVIEW_RESUME, err or status)
    if status in ("blocked_resume_verification", "failed"):
        return RunnerOutcome("failed", JobQueueState.BLOCKED, err or status)
    if status == "skipped":
        return RunnerOutcome("failed", JobQueueState.BLOCKED, err or status)
    if status == "dry_run":
        return RunnerOutcome("stopped_review_required", JobQueueState.REVIEW_RESUME, "dry_run_complete")

    return RunnerOutcome("failed", JobQueueState.BLOCKED, err or status or "apply_failed")
