"""
Phase 10 — One-by-one approved queue runner.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from services.apply_queue_service import (
    get_queue,
    set_job_state,
    mark_applied,
    mark_blocked,
    mark_runner_started,
    set_runner_state,
    JobQueueState,
)
from services.resume_upload_binding import ensure_bound_resume_or_block
from services.runner_guardrails import validate_queue_item, classify_apply_payload


@dataclass
class RunnerConfig:
    dry_run: bool = False
    max_jobs: int = 25
    rate_limit_seconds: float = 5.0
    require_safeguards: bool = True
    manual_assist: bool = False


def run_approved_queue(config: Optional[RunnerConfig] = None) -> dict:
    if config is None:
        config = RunnerConfig()

    approved = get_queue(states=[JobQueueState.APPROVED_FOR_APPLY], limit=config.max_jobs)
    if not approved:
        return {
            "status": "ok",
            "processed": 0,
            "results": [],
            "message": "No approved jobs in queue.",
        }

    results = []
    for idx, item in enumerate(approved):
        item_id = item.get("id", "")
        job_title = item.get("job_title", "")
        company = item.get("company", "")
        job_url = item.get("job_url", "")

        if idx > 0:
            time.sleep(max(1.0, config.rate_limit_seconds))

        mark_runner_started(item_id)
        set_job_state(item_id, JobQueueState.APPLYING)

        validation = validate_queue_item(item)
        if not validation.ok:
            set_runner_state(item_id, "failed", validation.error)
            mark_blocked(item_id, validation.error)
            results.append({
                "item_id": item_id,
                "job_title": job_title,
                "company": company,
                "status": "failed",
                "error": validation.error,
            })
            continue

        bound = ensure_bound_resume_or_block(item_id)
        if bound.get("status") != "ok":
            err = bound.get("message", "missing approved resume")
            set_runner_state(item_id, "failed", err)
            mark_blocked(item_id, err)
            results.append({
                "item_id": item_id,
                "job_title": job_title,
                "company": company,
                "status": "failed",
                "error": err,
            })
            continue

        version = bound.get("version") or {}
        approved_resume_path = version.get("approved_pdf_path") or item.get("approved_resume_path", "")

        from services.linkedin_browser_automation import apply_to_jobs_payload
        jobs_payload = [{
            "job_id": item_id,
            "url": job_url,
            "title": job_title,
            "company": company,
            "apply_url": job_url,
            "fit_decision": "apply",
            "ats_score": item.get("final_ats_score", item.get("ats_score", 85)),
            "fit_state": item.get("fit_decision", ""),
            "package_state": item.get("package_status", ""),
            "approval_state": item.get("approval_status", ""),
            "queue_state": item.get("job_state", ""),
            "runner_state": item.get("runner_state", ""),
            "approved_resume_path": approved_resume_path,
            "resume_path": approved_resume_path,
            "easy_apply_confirmed": bool(item.get("easy_apply_confirmed", False)),
        }]

        payload = apply_to_jobs_payload(
            jobs=jobs_payload,
            dry_run=config.dry_run,
            shadow_mode=False,
            rate_limit_seconds=config.rate_limit_seconds,
            manual_assist=config.manual_assist,
            require_safeguards=config.require_safeguards,
        )

        outcome = classify_apply_payload(payload)
        set_runner_state(item_id, outcome.runner_state, outcome.error)

        if outcome.job_state == JobQueueState.APPLIED:
            mark_applied(item_id)
        elif outcome.job_state == JobQueueState.REVIEW_RESUME:
            set_job_state(item_id, JobQueueState.REVIEW_RESUME, notes=outcome.error)
        elif outcome.job_state == JobQueueState.BLOCKED:
            mark_blocked(item_id, outcome.error)
        elif outcome.job_state == JobQueueState.APPROVED_FOR_APPLY:
            set_job_state(item_id, JobQueueState.APPROVED_FOR_APPLY, notes=outcome.error)

        results.append({
            "item_id": item_id,
            "job_title": job_title,
            "company": company,
            "job_url": job_url,
            "runner_state": outcome.runner_state,
            "job_state": outcome.job_state,
            "error": outcome.error,
        })

    summary = {
        "submitted": sum(1 for r in results if r.get("runner_state") == "submitted"),
        "failed": sum(1 for r in results if r.get("runner_state") == "failed"),
        "stopped_review_required": sum(1 for r in results if r.get("runner_state") == "stopped_review_required"),
        "retry_needed": sum(1 for r in results if r.get("runner_state") == "retry_needed"),
    }

    return {
        "status": "ok",
        "processed": len(results),
        "summary": summary,
        "results": results,
    }
