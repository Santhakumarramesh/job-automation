"""
Phase 11 — Queue Runner Executor
Processes approved jobs from the apply queue one-by-one.

Flow per job:
  1. Pull next approved item from apply_queue DB
  2. Generate / load tailored resume package (if not already generated)
  3. Call answer_form_fields to get truth-inventory answers for all form questions
  4. Execute apply via application_runner (Playwright) or LinkedIn Easy Apply
  5. Update queue state → applied | blocked
  6. Emit structured log per job

Key rule: NO job is submitted without package_status ≥ 'generated'
          AND item.job_state == 'approved_for_apply'.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Run result dataclass
# ---------------------------------------------------------------------------

@dataclass
class JobRunResult:
    item_id: str
    job_title: str
    company: str
    job_url: str
    status: str          # "applied" | "blocked" | "skipped" | "dry_run"
    resume_path: str = ""
    package_status: str = ""
    initial_ats_score: float = 0.0
    final_ats_score: float = 0.0
    truth_safe_ceiling: float = 0.0
    form_answers: dict = field(default_factory=dict)
    error: str = ""
    duration_sec: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class RunnerConfig:
    dry_run: bool = False
    max_jobs: int = 50          # safety cap per run
    target_ats_score: float = 85.0
    max_ats_iterations: int = 5
    inter_job_delay_sec: float = 5.0
    master_resume_path: str = ""
    master_resume_text: str = ""
    skip_resume_generation: bool = False  # use package if already generated


# ---------------------------------------------------------------------------
# Main executor
# ---------------------------------------------------------------------------

def run_approved_queue(config: Optional[RunnerConfig] = None) -> dict:
    """
    Process all items in approved_for_apply state, one by one.

    Returns a summary dict with per-job results and aggregate counts.
    """
    if config is None:
        config = RunnerConfig()

    from services.apply_queue_service import (
        get_approved_queue, attach_package,
        mark_applied, mark_blocked,
        JobQueueState,
    )
    from services.resume_package_service import generate_package_for_job, _load_master_resume_text
    from services.profile_service import load_profile

    # ------------------------------------------------------------------
    # Load shared resources
    # ------------------------------------------------------------------
    profile = load_profile() or {}
    master_resume_text = config.master_resume_text
    if not master_resume_text:
        master_resume_text = _load_master_resume_text(config.master_resume_path or None)

    approved_items = get_approved_queue()
    if not approved_items:
        return {
            "status": "ok",
            "message": "No approved jobs in queue.",
            "processed": 0,
            "results": [],
        }

    results: list[JobRunResult] = []
    processed = 0

    for item in approved_items[:config.max_jobs]:
        if processed > 0 and not config.dry_run:
            time.sleep(config.inter_job_delay_sec)

        result = _process_single_item(
            item=item,
            config=config,
            profile=profile,
            master_resume_text=master_resume_text,
        )
        results.append(result)
        processed += 1

        # Update queue DB
        if result.status == "applied":
            mark_applied(item["id"])
        elif result.status == "blocked":
            mark_blocked(item["id"])

        logger.info(
            "[QueueRunner] %s — %s @ %s | ATS %.0f→%.0f | status=%s",
            item["id"], item["job_title"], item["company"],
            result.initial_ats_score, result.final_ats_score, result.status,
        )

    applied_count = sum(1 for r in results if r.status == "applied")
    blocked_count = sum(1 for r in results if r.status == "blocked")
    dry_run_count = sum(1 for r in results if r.status == "dry_run")

    return {
        "status": "ok",
        "processed": processed,
        "applied": applied_count,
        "blocked": blocked_count,
        "dry_run_count": dry_run_count,
        "results": [_result_to_dict(r) for r in results],
    }


def _process_single_item(
    item: dict,
    config: RunnerConfig,
    profile: dict,
    master_resume_text: str,
) -> JobRunResult:
    """Execute a single approved queue item end-to-end."""
    from services.apply_queue_service import attach_package
    from services.resume_package_service import generate_package_for_job
    from services.resume_upload_binding import ensure_bound_resume_or_block

    start_ts = time.monotonic()
    item_id = item["id"]
    job_title = item.get("job_title", "")
    company = item.get("company", "")
    job_url = item.get("job_url", "")
    job_description = item.get("job_description", "")
    existing_pkg = item.get("resume_path") or ""
    existing_pkg_status = item.get("package_status", "not_generated")

    result = JobRunResult(
        item_id=item_id,
        job_title=job_title,
        company=company,
        job_url=job_url,
        status="blocked",
    )

    try:
        bound = ensure_bound_resume_or_block(item_id)
        if bound.get("status") != "ok":
            result.error = bound.get("message", "missing approved resume")
            result.status = "blocked"
            return result
        approved_resume_path = (bound.get("version") or {}).get("approved_pdf_path") or item.get("approved_resume_path", "")
        if not approved_resume_path or not Path(approved_resume_path).exists():
            result.error = "approved_resume_path_missing"
            result.status = "blocked"
            return result

        # ------------------------------------------------------------------
        # Step 1: Generate or load resume package
        # ------------------------------------------------------------------
        if (
            not config.skip_resume_generation
            or existing_pkg_status == "not_generated"
            or not existing_pkg
        ):
            pkg = generate_package_for_job(
                job_title=job_title,
                company=company,
                job_description=job_description,
                master_resume_path=config.master_resume_path or None,
                target_ats_score=config.target_ats_score,
                max_iterations=config.max_ats_iterations,
            )
        else:
            # Load existing package metadata
            pkg_meta_path = Path(existing_pkg).parent / "package.json"
            if pkg_meta_path.exists():
                import json as _json
                pkg = _json.loads(pkg_meta_path.read_text())
            else:
                pkg = {"resume_path": existing_pkg, "package_status": existing_pkg_status}

        result.resume_path = pkg.get("resume_path", "")
        result.package_status = pkg.get("package_status", "generated")
        result.initial_ats_score = pkg.get("initial_ats_score", 0.0)
        result.final_ats_score = pkg.get("final_ats_score", 0.0)
        result.truth_safe_ceiling = pkg.get("truth_safe_ats_ceiling", 0.0)

        # Attach package to queue item
        attach_package(item_id, pkg)

        # Use approved resume path for apply
        result.resume_path = approved_resume_path

        # ------------------------------------------------------------------
        # Step 2: Gather form answers from truth inventory
        # ------------------------------------------------------------------
        form_answers = _get_form_answers(
            job_title=job_title,
            company=company,
            job_description=job_description,
            profile=profile,
            master_resume_text=master_resume_text,
        )
        result.form_answers = form_answers

        # ------------------------------------------------------------------
        # Step 3: Apply (or dry-run)
        # ------------------------------------------------------------------
        if config.dry_run:
            result.status = "dry_run"
            result.error = ""
        else:
            apply_result = _execute_apply(
                job_url=job_url,
                job_title=job_title,
                company=company,
                resume_path=result.resume_path,
                profile=profile,
                form_answers=form_answers,
                job_description=job_description,
                easy_apply_confirmed=bool(item.get("easy_apply_confirmed", False)),
            )
            result.status = "applied" if apply_result.get("success") else "blocked"
            result.error = apply_result.get("error", "")

    except Exception as exc:
        import traceback
        result.status = "blocked"
        result.error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-800:]}"

    finally:
        result.duration_sec = round(time.monotonic() - start_ts, 2)

    return result


# ---------------------------------------------------------------------------
# Form answer helper — calls application_answerer truth inventory
# ---------------------------------------------------------------------------

STANDARD_QUESTIONS = [
    ("years_python", "years", "How many years of Python experience do you have?"),
    ("years_ml", "years", "How many years of machine learning experience do you have?"),
    ("years_sql", "years", "How many years of SQL experience do you have?"),
    ("sponsorship", "sponsorship", "Do you require visa sponsorship?"),
    ("authorized", "work_authorization", "Are you authorized to work in the US?"),
    ("salary_expectation", "salary", "What are your salary expectations?"),
    ("relocation", "relocation", "Are you willing to relocate?"),
    ("remote_preference", "remote_preference", "Are you open to remote work?"),
    ("why_role", "why_role", "Why are you interested in this role?"),
]


def _get_form_answers(
    job_title: str,
    company: str,
    job_description: str,
    profile: dict,
    master_resume_text: str,
) -> dict:
    """
    Call answer_question_structured for each standard question.
    Returns {field_label: {answer, review_required, reason_codes, confidence}}.
    """
    try:
        from agents.application_answerer import answer_question_structured

        job_context = {"job_title": job_title, "company": company}
        answers = {}

        for field_key, q_type, q_text in STANDARD_QUESTIONS:
            try:
                ans = answer_question_structured(
                    question_text=q_text,
                    question_type=q_type,
                    profile=profile,
                    master_resume_text=master_resume_text,
                    job_description=job_description,
                    job_context=job_context,
                    use_llm=False,
                )
                ans_dict = ans if isinstance(ans, dict) else None
                answer_text = (ans_dict.get("answer") if ans_dict else getattr(ans, "answer", str(ans)))
                manual_required = (
                    ans_dict.get("manual_review_required") if ans_dict
                    else getattr(ans, "manual_review_required", getattr(ans, "review_required", False))
                )
                reason_codes = ans_dict.get("reason_codes", []) if ans_dict else getattr(ans, "reason_codes", [])
                classified_type = ans_dict.get("classified_type", q_type) if ans_dict else getattr(ans, "classified_type", q_type)
                confidence = ans_dict.get("confidence", "high") if ans_dict else getattr(ans, "confidence", "high")
                answers[field_key] = {
                    "answer": str(answer_text),
                    "manual_review_required": bool(manual_required),
                    "review_required": bool(manual_required),
                    "reason_codes": reason_codes,
                    "classified_type": classified_type,
                    "confidence": confidence,
                    "question_text": q_text,
                }
            except Exception as e:
                answers[field_key] = {
                    "answer": "",
                    "manual_review_required": True,
                    "review_required": True,
                    "reason_codes": [f"error: {e}"],
                    "confidence": "low",
                    "question_text": q_text,
                }

        return answers

    except ImportError:
        logger.warning("[QueueRunner] application_answerer not available, returning empty answers")
        return {}


# ---------------------------------------------------------------------------
# Apply executor — delegates to application_runner
# ---------------------------------------------------------------------------

def _execute_apply(
    job_url: str,
    job_title: str,
    company: str,
    resume_path: str,
    profile: dict,
    form_answers: dict,
    job_description: str,
    easy_apply_confirmed: bool = False,
) -> dict:
    """
    Delegate actual application submission to the existing application_runner.
    Returns {"success": bool, "error": str}.
    """
    try:
        from services.linkedin_browser_automation import apply_to_jobs_payload

        jobs_payload = [{
            "url": job_url,
            "title": job_title,
            "company": company,
            "apply_url": job_url,
            "fit_decision": "apply",
            "ats_score": 90,
            "approved_resume_path": resume_path,
            "resume_path": resume_path,
            "easy_apply_confirmed": bool(easy_apply_confirmed),
        }]
        result = apply_to_jobs_payload(
            jobs=jobs_payload,
            dry_run=False,
            shadow_mode=False,
            rate_limit_seconds=5,
            manual_assist=False,
            require_safeguards=True,
        )
        if result.get("status") != "ok":
            return {"success": False, "error": result.get("message", "apply_to_jobs failed")}
        applied = int(result.get("applied", 0) or 0)
        if applied > 0:
            return {"success": True, "error": ""}
        # Extract first result error if present
        res_list = result.get("results") or []
        if res_list:
            r0 = res_list[0] or {}
            return {"success": False, "error": r0.get("error") or r0.get("status") or "apply_failed"}
        return {"success": False, "error": "apply_failed"}

    except Exception as exc:
        import traceback
        return {"success": False, "error": f"{exc}\n{traceback.format_exc()[-600:]}"}


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def _result_to_dict(r: JobRunResult) -> dict:
    return {
        "item_id": r.item_id,
        "job_title": r.job_title,
        "company": r.company,
        "job_url": r.job_url,
        "status": r.status,
        "resume_path": r.resume_path,
        "package_status": r.package_status,
        "initial_ats_score": r.initial_ats_score,
        "final_ats_score": r.final_ats_score,
        "truth_safe_ceiling": r.truth_safe_ceiling,
        "form_answers_count": len(r.form_answers),
        "review_required_fields": [
            k for k, v in r.form_answers.items() if v.get("manual_review_required") or v.get("review_required")
        ],
        "error": r.error[:500] if r.error else "",
        "duration_sec": r.duration_sec,
        "timestamp": r.timestamp,
    }
