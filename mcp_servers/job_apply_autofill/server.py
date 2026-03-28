#!/usr/bin/env python3
"""
Career Copilot MCP — supervised candidate-ops policy server.

This MCP is the POLICY + PACKAGE ENGINE of the Career Co-Pilot Pro platform.
It is NOT an autonomous apply bot. It implements a supervised, truth-gated
application workflow:

  - Truth inventory → fit scoring → ATS alignment → package generation
  - LinkedIn Easy Apply: policy-gated assisted or supervised submit
  - Workday / Greenhouse / Lever: manual_assist only (system prepares; human submits)

Job states: skip | manual_review | manual_assist | safe_auto_apply | blocked
Answer states: safe | review | missing | blocked
Safety gates: truth_safe AND submit_safe → safe_to_submit

See docs/PRODUCT_BRIEF.md for positioning, docs/AUTONOMY_MODEL.md for policy model.

Requires: pip install fastmcp playwright mcp
Then: playwright install chromium
"""

import json
import os
import sys
from pathlib import Path

# Add project root for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from fastmcp import FastMCP
except ImportError:
    print("Install: pip install fastmcp", file=sys.stderr)
    sys.exit(1)

_MCP_INSTRUCTIONS = (
    "Career Copilot MCP — supervised candidate-ops policy engine. "
    "Truth-safe job fit scoring, ATS alignment, tailored package generation, and "
    "policy-gated assisted submission. LinkedIn Easy Apply (supervised/shadow/pilot). "
    "External ATS (Workday/Greenhouse/Lever) = manual_assist only. "
    "See docs/PRODUCT_BRIEF.md and docs/AUTONOMY_MODEL.md."
)
try:
    mcp = FastMCP("Career Copilot MCP", description=_MCP_INSTRUCTIONS)
except TypeError:
    # fastmcp >=2: ``description`` removed; optional ``instructions`` on some versions
    try:
        mcp = FastMCP("Career Copilot MCP", instructions=_MCP_INSTRUCTIONS)
    except TypeError:
        mcp = FastMCP("Career Copilot MCP")


@mcp.tool()
def prepare_resume_for_job(
    job_title: str,
    company: str,
    resume_source_path: str = "",
) -> dict:
    """
    Prepare resume with job-specific naming: {Name}_{Position}_at_{Company}_Resume.pdf.
    Copies from source or Master_Resumes to generated_resumes/{Company}/.
    Returns dict with resume_path, filename.
    """
    try:
        from services.prepare_resume_for_job import prepare_resume_for_job_payload

        return prepare_resume_for_job_payload(job_title, company, resume_source_path)
    except Exception as e:
        return {"resume_path": "", "status": "error", "message": str(e)[:200]}


@mcp.tool()
def get_autofill_values(
    form_type: str = "linkedin",
    question_hints: str = "",
) -> dict:
    """
    Get suggested autofill values for form fields from candidate profile.
    form_type: linkedin, greenhouse, lever, workday, generic.
    question_hints: optional comma-separated hints (e.g. 'sponsorship, salary, years experience').
    Returns dict mapping field names to values.
    """
    try:
        from services.autofill_values import get_autofill_values_payload

        return get_autofill_values_payload(form_type=form_type, question_hints=question_hints)
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}


@mcp.tool()
def apply_to_jobs(
    jobs_json: str,
    dry_run: bool = False,
    shadow_mode: bool = False,
    rate_limit_seconds: float = 90.0,
    manual_assist: bool = False,
    require_safeguards: bool = True,
) -> dict:
    """
    Apply to jobs from JSON. By default: Easy Apply only, no external ATS.
    jobs_json: JSON string, list of job objects (url, title, company, …). Optional ``pilot_submit_allowed: true`` for Phase 3 pilot-only live submit when ``AUTONOMY_LINKEDIN_PILOT_SUBMIT_ONLY=1``.
    dry_run: if True, fill forms but do not submit. Recommended for first run.
    shadow_mode: Phase 2 — fill through pre-submit, never submit; statuses ``shadow_would_apply`` /
    ``shadow_would_not_apply`` (tracker + run JSON). Overrides dry-run labeling when both True.
    rate_limit_seconds: min seconds between applications (default 90).
    manual_assist: if True, allow external ATS (Greenhouse, Lever, Workday). Default False = Easy Apply only.
    require_safeguards: if True, skip jobs without fit_decision=apply and ats_score>=85 when provided.
    Requires LINKEDIN_EMAIL, LINKEDIN_PASSWORD. Resume from Master_Resumes or RESUME_PATH.
    """
    try:
        from services.linkedin_browser_automation import apply_to_jobs_payload

        return apply_to_jobs_payload(
            jobs_json,
            dry_run=dry_run,
            shadow_mode=shadow_mode,
            rate_limit_seconds=rate_limit_seconds,
            manual_assist=manual_assist,
            require_safeguards=require_safeguards,
            project_root=PROJECT_ROOT,
        )
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@mcp.tool()
def detect_form_type(url: str) -> dict:
    """
    Detect application form type from URL.
    Returns: linkedin, greenhouse, lever, workday, or generic.
    """
    try:
        from services.form_type_detection import detect_form_type_payload

        return detect_form_type_payload(url)
    except Exception as e:
        return {"url": url or "", "form_type": "generic", "error": str(e)[:100]}


# --- Decision tools ---

@mcp.tool()
def decide_apply_mode(
    job_json: str,
    fit_decision: str = "",
    ats_score: str = "",
    unsupported_requirements_json: str = "[]",
) -> dict:
    """
    Central decision: auto_easy_apply | manual_assist | skip.
    job_json: JSON object with url, easy_apply_confirmed, optional fit/ATS fields,
    and optional answerer_preview: answerer_manual_review_required (bool) and/or
    answerer_review (object of field → {manual_review_required, ...}) to downgrade auto → manual_assist.
    Returns apply_mode and reason.
    """
    try:
        from services.policy_service import decide_apply_mode_payload

        job = json.loads(job_json) if isinstance(job_json, str) else (job_json or {})
        ats = int(ats_score) if ats_score and str(ats_score).strip() else None
        unsup = json.loads(unsupported_requirements_json) if isinstance(unsupported_requirements_json, str) else []
        return decide_apply_mode_payload(
            job=job,
            fit_decision=fit_decision or "",
            ats_score=ats,
            unsupported_requirements=unsup,
        )
    except Exception as e:
        return {"apply_mode": "manual_assist", "policy_reason": "error", "status": "error", "message": str(e)[:150]}


@mcp.tool()
def get_application_decision(
    job_json: str,
    profile_path: str = "",
    master_resume_text: str = "",
    blocked_reason: str = "",
) -> dict:
    """
    Unified v0.1 decision: job_state (skip | manual_assist | safe_auto_apply | blocked),
    safe_to_submit, apply_mode_legacy, policy_reason, fit_decision, per-field answer_state,
    truth_safe, submit_safe, critical_unsatisfied. Runs canonical answerer preview + policy
    (same as Streamlit export). blocked_reason: optional runner hard-stop (forces blocked).
    """
    try:
        from services.application_decision import build_application_decision
        from services.profile_service import load_profile

        job = json.loads(job_json) if isinstance(job_json, str) else (job_json or {})
        prof = load_profile(profile_path.strip() or None)
        br = (blocked_reason or "").strip() or None
        return build_application_decision(
            job,
            profile=prof,
            master_resume_text=master_resume_text or "",
            use_llm_preview=False,
            blocked_reason=br,
        )
    except Exception as e:
        return {
            "schema_version": "0.1",
            "job_state": "blocked",
            "safe_to_submit": False,
            "status": "error",
            "message": str(e)[:200],
        }


@mcp.tool()
def validate_candidate_profile(profile_path: str = "") -> dict:
    """
    Validate candidate profile. Checks full_name, email, phone, linkedin_url,
    github_url, portfolio_url, work_authorization_note, notice_period, short_answers.
    Returns warnings, auto_apply_ready, and suggested fixes.
    """
    try:
        from services.profile_service import validate_candidate_profile_payload

        return validate_candidate_profile_payload(
            profile_path or "",
            restrict_to_project_relative=False,
        )
    except Exception as e:
        return {"status": "error", "auto_apply_ready": False, "message": str(e)[:200]}


@mcp.tool()
def build_truth_inventory_from_master_resume(
    master_resume_text: str = "",
    master_resume_path: str = "",
) -> dict:
    """
    Parse master resume into a JSON-serializable truth inventory (skills, tools, projects,
    companies, locations, visa hints, URLs). Same core as the fit gate / ATS guard.
    Provide either ``master_resume_text`` (>=100 chars) or ``master_resume_path`` (.pdf/.md/.txt),
    or rely on RESUME_PATH / MASTER_RESUME_PDF / Master_Resumes/*.
    """
    try:
        from agents.master_resume_guard import (
            load_master_resume_text,
            parse_master_resume,
            truth_inventory_from_profile,
        )

        text, src = load_master_resume_text(path=master_resume_path, inline_text=master_resume_text)
        if len(text.strip()) < 100:
            return {
                "status": "error",
                "message": "Need master resume text (100+ chars) or a readable path / Master_Resumes file.",
                "inventory": {},
                "source": src or "",
            }
        profile = parse_master_resume(text)
        return {
            "status": "ok",
            "source": src or "inline_text",
            "char_count": len(text),
            "inventory": truth_inventory_from_profile(profile),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)[:200], "inventory": {}}


@mcp.tool()
def search_jobs(
    keywords: str = "",
    location: str = "United States",
    work_type: str = "remote",
    max_results: int = 25,
    easy_apply: bool = False,
    date_posted: str = "",
    job_type: str = "",
    experience_level: str = "",
    sort_order: str = "",
) -> dict:
    """
    Discover jobs via LinkedIn MCP (linkedin-mcp-server) and return normalized job rows.
    Requires ``LINKEDIN_MCP_URL`` (default http://127.0.0.1:8000/mcp) and a running server.
    Each item matches the shared job schema (title, company, url, easy_apply_confirmed, source, etc.).
    """
    try:
        from providers.linkedin_mcp_jobs import linkedin_mcp_search_jobs_payload

        return linkedin_mcp_search_jobs_payload(
            keywords=keywords,
            location=location or "United States",
            work_type=work_type or "remote",
            max_results=max_results,
            easy_apply=bool(easy_apply),
            date_posted=date_posted or "",
            job_type=job_type or "",
            experience_level=experience_level or "",
            sort_order=sort_order or "",
        )
    except Exception as e:
        return {"status": "error", "message": str(e)[:200], "jobs": [], "count": 0}


@mcp.tool()
def score_job_fit(
    job_description: str,
    master_resume_text: str,
    job_title: str = "",
    company: str = "",
    location: str = "USA",
) -> dict:
    """
    Score job fit before applying. Returns fit_score, fit_decision, missing_keywords,
    unsupported_requirements, ats_feasibility. Uses master resume guard + ATS checker.
    """
    try:
        from services.ats_service import score_job_fit_payload

        return score_job_fit_payload(
            job_description=job_description,
            master_resume_text=master_resume_text,
            job_title=job_title,
            company=company,
            location=location,
        )
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}


@mcp.tool()
def confirm_easy_apply(job_url: str) -> dict:
    """
    Open job page (after LinkedIn login) and confirm Easy Apply button exists.
    Returns easy_apply_confirmed, matched_selector (if any), selectors_tried.
    Requires LINKEDIN_EMAIL, LINKEDIN_PASSWORD. Prefer a ``linkedin.com/jobs/...`` URL.
    """
    try:
        from services.linkedin_browser_automation import confirm_easy_apply_payload

        return confirm_easy_apply_payload(job_url)
    except Exception as e:
        return {"easy_apply_confirmed": False, "status": "error", "message": str(e)[:200]}


# --- Execution tools ---


@mcp.tool()
def analyze_form(
    job_url: str = "",
    apply_url: str = "",
) -> dict:
    """
    Return ATS adapter form analysis (v1 static section hints) plus platform metadata.
    For live DOM scraping per board, extend ``providers/ats`` implementations.
    """
    try:
        from services.ats_form_analysis import run_analyze_form

        return run_analyze_form(job_url=job_url, apply_url=apply_url)
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}


@mcp.tool()
def analyze_form_live(
    job_url: str = "",
    apply_url: str = "",
    max_fields: int = 40,
) -> dict:
    """
    Optional read-only DOM probe (headless Chromium): input/select/textarea metadata.
    Requires env ``ATS_ALLOW_LIVE_FORM_PROBE=1`` and Playwright + ``playwright install chromium``.
    """
    try:
        from services.ats_form_analysis import run_analyze_form
        from services.live_form_probe import (
            live_form_probe_disabled_response,
            live_form_probe_enabled,
            probe_apply_page_fields,
        )

        if not live_form_probe_enabled():
            return live_form_probe_disabled_response()
        target = (apply_url or job_url or "").strip()
        if not target:
            return {"status": "error", "message": "apply_url or job_url required"}
        live = probe_apply_page_fields(target, max_fields=max(5, min(int(max_fields), 120)))
        static = run_analyze_form(job_url=job_url.strip(), apply_url=apply_url.strip())
        return {"status": "ok", "live": live, "static": static}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}


@mcp.tool()
def describe_ats_platform(
    job_url: str = "",
    apply_url: str = "",
) -> dict:
    """
    ATS/board summary: provider labels, whether v1 auto-submit is allowed (LinkedIn jobs only),
    manual-assist capabilities, and a stub analyze_form preview.
    """
    try:
        from providers.ats.registry import describe_ats_platform as describe

        return {"status": "ok", **describe(job_url=job_url, apply_url=apply_url)}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}


@mcp.tool()
def get_address_for_job(
    job_location: str = "",
    job_title: str = "",
    job_description: str = "",
    work_type: str = "",
) -> dict:
    """
    Pick default or alternate mailing address from candidate profile based on job location text.
    Uses mailing_address and optional alternate_mailing_addresses[].regions_served.
    """
    try:
        from services.address_for_job import address_for_job_payload

        return address_for_job_payload(
            job_location=job_location,
            job_title=job_title,
            job_description=job_description,
            work_type=work_type,
        )
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}


@mcp.tool()
def prepare_application_package(
    job_title: str,
    company: str,
    job_description: str = "",
    master_resume_text: str = "",
    job_location: str = "",
    work_type: str = "",
) -> dict:
    """
    Prepare full application package for manual-assist lane: job-specific resume path,
    cover letter path (if generated), autofill values, short answers, fit decision, ATS score.
    """
    try:
        from services.application_package import prepare_application_package_payload

        return prepare_application_package_payload(
            job_title=job_title,
            company=company,
            job_description=job_description,
            master_resume_text=master_resume_text,
            job_location=job_location,
            work_type=work_type,
        )
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}


@mcp.tool()
def dry_run_apply_to_jobs(jobs_json: str, rate_limit_seconds: float = 90.0) -> dict:
    """
    Fill forms without submitting. Safe testing. Fills fields, takes screenshots,
    saves unmapped fields. Never submits.
    """
    return apply_to_jobs(jobs_json=jobs_json, dry_run=True, rate_limit_seconds=rate_limit_seconds)


@mcp.tool()
def review_unmapped_fields(run_results_path: str) -> dict:
    """
    Summarize unmapped fields from a run. Returns which fields were missed,
    likely question types, and suggested profile keys to add.
    """
    try:
        from services.run_results_reports import review_unmapped_fields_payload

        path = Path(run_results_path)
        if not path.is_file():
            return {"status": "error", "message": f"File not found: {run_results_path}"}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return review_unmapped_fields_payload(data)
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}


@mcp.tool()
def batch_prioritize_jobs(
    jobs_json: str,
    master_resume_text: str,
    max_scored: int = 20,
) -> dict:
    """
    Rank jobs by fit score, ATS potential, easy_apply_confirmed. Returns sorted list
    with fit_score, fit_decision, ats_score for each. Limits to max_scored to avoid long runs.
    """
    try:
        from services.batch_prioritize_jobs import batch_prioritize_jobs_payload

        jobs = json.loads(jobs_json) if isinstance(jobs_json, str) else jobs_json
        return batch_prioritize_jobs_payload(jobs, master_resume_text, max_scored=max_scored)
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}


@mcp.tool()
def generate_recruiter_followup(
    job_title: str,
    company: str,
    application_date: str = "",
) -> dict:
    """
    Generate recruiter follow-up: short LinkedIn message and email. Uses candidate profile.
    """
    try:
        from services.recruiter_followup import generate_recruiter_followup_payload

        return generate_recruiter_followup_payload(
            job_title=job_title,
            company=company,
            application_date=application_date,
        )
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}


@mcp.tool()
def application_audit_report(run_results_path: str) -> dict:
    """
    After a batch run, return applied count, skipped count, fail reasons,
    unmapped fields summary, profile gaps, next recommended fixes.
    """
    try:
        from services.run_results_reports import application_audit_report_payload

        path = Path(run_results_path)
        if not path.is_file():
            return {"status": "error", "message": f"File not found: {run_results_path}"}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return application_audit_report_payload(data)
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}



# =============================================================================
# Phase 11 — Production-Ready Apply Queue Tools
# =============================================================================

@mcp.tool()
def answer_form_fields(
    fields_json: str,
    job_title: str = "",
    company: str = "",
    job_description: str = "",
    master_resume_text: str = "",
) -> dict:
    """
    Given a JSON list of form field labels/questions detected in the DOM,
    answer each one from the truth inventory (profile + master resume).
    Returns {field_label: {answer, review_required, source, confidence}}.
    
    fields_json: JSON array of strings (field labels or questions), e.g.
      ["How many years of Python experience?", "Are you authorized to work in the US?"]
    """
    try:
        import json as _json
        from agents.application_answerer import answer_question_structured
        from services.profile_service import load_profile

        fields = _json.loads(fields_json) if isinstance(fields_json, str) else fields_json
        profile = load_profile() or {}
        job_ctx = {"company": company, "title": job_title}
        results = {}

        for field_label in fields:
            if not field_label:
                continue
            meta = answer_question_structured(
                question_text=str(field_label),
                profile=profile,
                master_resume_text=master_resume_text,
                job_description=job_description,
                job_context=job_ctx,
                use_llm=bool(os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")),
            )
            results[str(field_label)] = {
                "answer": meta["answer"],
                "review_required": meta["manual_review_required"],
                "reason_codes": meta["reason_codes"],
                "classified_type": meta["classified_type"],
                "confidence": "high" if not meta["manual_review_required"] else "low",
            }

        return {"status": "ok", "answers": results, "total_fields": len(results)}
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@mcp.tool()
def get_saved_answer(
    question_text: str,
    job_context_json: str = "",
) -> dict:
    """
    Retrieve an approved answer from memory (if available).
    Memory never bypasses truth/policy gates; use `answer_form_fields` for full gating.
    """
    try:
        from services.answer_memory_store import get_saved_answer as _get

        ctx = {}
        if job_context_json:
            try:
                ctx = json.loads(job_context_json)
            except json.JSONDecodeError:
                ctx = {}

        res = _get(question_text=question_text, job_context=ctx)
        return {"status": "ok", **res}
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@mcp.tool()
def save_approved_answer(
    question_text: str,
    approved_answer: str,
    context_json: str = "",
    answer_state: str = "safe",
    source: str = "user_approved",
    approved_by: str = "user",
    confidence: str = "high",
    auto_use_allowed: bool = True,
) -> dict:
    """
    Persist a user-approved answer to memory.
    """
    try:
        from services.answer_memory_store import save_approved_answer as _save

        ctx = {}
        if context_json:
            try:
                ctx = json.loads(context_json)
            except json.JSONDecodeError:
                ctx = {"raw": context_json}

        result = _save(
            question_text=question_text,
            approved_answer=approved_answer,
            context=ctx,
            answer_state=answer_state,
            source=source,
            approved_by=approved_by,
            confidence=confidence,
            auto_use_allowed=auto_use_allowed,
        )
        return {"status": "ok", **result}
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@mcp.tool()
def list_answer_memory(limit: int = 200) -> dict:
    """
    List stored approved answers (current memory).
    """
    try:
        from services.answer_memory_store import list_answer_memory as _list

        rows = _list(limit=limit)
        return {"status": "ok", "count": len(rows), "items": rows}
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@mcp.tool()
def mark_answer_requires_review(question_key: str) -> dict:
    """
    Mark a saved answer as review-required (disables auto-use).
    """
    try:
        from services.answer_memory_store import mark_answer_requires_review as _mark

        ok = _mark(question_key)
        return {"status": "ok", "updated": bool(ok)}
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@mcp.tool()
def suggest_answer_from_memory(
    fields_json: str,
    job_context_json: str = "",
) -> dict:
    """
    Suggest answers from memory for a list of field labels/questions.
    """
    try:
        fields = json.loads(fields_json) if isinstance(fields_json, str) else fields_json
        ctx = {}
        if job_context_json:
            try:
                ctx = json.loads(job_context_json)
            except json.JSONDecodeError:
                ctx = {}
        from services.answer_memory_store import suggest_answers_from_memory

        suggestions = suggest_answers_from_memory(list(fields or []), job_context=ctx)
        return {"status": "ok", "suggestions": suggestions, "total_fields": len(fields or [])}
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@mcp.tool()
def get_autonomy_health(
    user_id: str = "",
    workspace_id: str = "",
    include_audit: bool = False,
) -> dict:
    """
    Return autonomy telemetry + gate status (kill switches, pilot-only flags, and Redis metrics).
    """
    try:
        from services.autonomy_control import read_live_submit_pause_state
        from services.truth_apply_gate import truth_apply_hard_gate_enabled
        from services.autonomy_submit_gate import linkedin_live_submit_block_reason
        from services.apply_runner_metrics_redis import (
            read_apply_runner_metrics_summary,
            read_linkedin_live_submit_totals,
            read_linkedin_nonsubmit_pattern_totals,
        )
        from services.application_insights import build_application_insights

        pause_state = read_live_submit_pause_state()
        live_block_reason = linkedin_live_submit_block_reason({})
        metrics = read_apply_runner_metrics_summary()
        totals = read_linkedin_live_submit_totals()
        nonsubmit = read_linkedin_nonsubmit_pattern_totals()

        insights = None
        if include_audit:
            insights = build_application_insights(
                for_user_id=user_id or None,
                workspace_id=workspace_id or None,
                include_audit=True,
            )

        return {
            "status": "ok",
            "live_submit_paused": bool(pause_state.get("paused")),
            "pause_state": pause_state,
            "live_block_reason": live_block_reason or "",
            "truth_apply_hard_gate": truth_apply_hard_gate_enabled(),
            "pilot_only_enabled": os.getenv("AUTONOMY_LINKEDIN_PILOT_SUBMIT_ONLY", "").lower() in ("1", "true", "yes"),
            "live_submit_disabled_env": os.getenv("AUTONOMY_LINKEDIN_LIVE_SUBMIT_DISABLED", "").lower() in ("1", "true", "yes"),
            "rollback_thresholds": {
                "failure_rate_gte": os.getenv("AUTONOMY_LINKEDIN_ROLLBACK_WHEN_FAILURE_RATE_GTE", ""),
                "failure_min_attempts": os.getenv("AUTONOMY_LINKEDIN_ROLLBACK_MIN_ATTEMPTS", "10"),
                "nonsubmit_rate_gte": os.getenv("AUTONOMY_LINKEDIN_ROLLBACK_WHEN_NONSUBMIT_RATE_GTE", ""),
                "nonsubmit_min_events": os.getenv("AUTONOMY_LINKEDIN_ROLLBACK_NONSUBMIT_MIN_EVENTS", "8"),
            },
            "redis_metrics": metrics,
            "live_submit_totals": {"attempt": totals[0], "success": totals[1]} if totals else None,
            "nonsubmit_pattern_totals": {"nonsubmit": nonsubmit[0], "denom": nonsubmit[1]} if nonsubmit else None,
            "insights": insights if include_audit else None,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@mcp.tool()
def get_shadow_vs_live_alignment(
    user_id: str = "",
    workspace_id: str = "",
) -> dict:
    """
    Return shadow-mode vs live apply alignment metrics from the tracker.
    """
    try:
        from services.application_tracker import load_applications
        from services.application_insights import compute_shadow_insights

        df = load_applications(
            for_user_id=user_id or None,
            workspace_id=workspace_id or None,
        )
        shadow = compute_shadow_insights(df)
        return {"status": "ok", "shadow": shadow}
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@mcp.tool()
def get_recent_submit_failures(
    limit: int = 20,
    user_id: str = "",
    workspace_id: str = "",
) -> dict:
    """
    Return recent failed/blocked submissions from the tracker.
    """
    try:
        import pandas as pd
        from services.application_tracker import load_applications

        df = load_applications(
            for_user_id=user_id or None,
            workspace_id=workspace_id or None,
        )
        if df.empty:
            return {"status": "ok", "count": 0, "items": []}

        df = df.fillna("")
        sub = df.get("submission_status")
        runner = df.get("runner_state") if "runner_state" in df.columns else None
        mask = sub.astype(str).str.contains("Failed|Skipped|Blocked|Error", case=False, regex=True)
        if runner is not None:
            mask = mask | runner.astype(str).str.lower().eq("failed")
        fail_df = df[mask].copy()
        if "applied_at" in fail_df.columns:
            fail_df["applied_at_ts"] = pd.to_datetime(fail_df["applied_at"], errors="coerce")
            fail_df = fail_df.sort_values(by="applied_at_ts", ascending=False)
        else:
            fail_df = fail_df.iloc[::-1]

        items = []
        for _, row in fail_df.head(int(limit)).iterrows():
            items.append(
                {
                    "applied_at": str(row.get("applied_at") or ""),
                    "company": str(row.get("company") or ""),
                    "position": str(row.get("position") or ""),
                    "submission_status": str(row.get("submission_status") or ""),
                    "policy_reason": str(row.get("policy_reason") or ""),
                    "job_url": str(row.get("job_url") or ""),
                    "runner_state": str(row.get("runner_state") or ""),
                    "final_state": str(row.get("final_state") or ""),
                }
            )

        return {"status": "ok", "count": len(items), "items": items}
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@mcp.tool()
def pause_live_submit(
    paused: bool = True,
    reason: str = "",
    updated_by: str = "operator",
) -> dict:
    """
    Pause or resume live submit via a file-backed override.
    """
    try:
        from services.autonomy_control import set_live_submit_paused

        state = set_live_submit_paused(paused, reason=reason, updated_by=updated_by)
        if paused:
            os.environ["AUTONOMY_LINKEDIN_LIVE_SUBMIT_DISABLED"] = "1"
        else:
            os.environ["AUTONOMY_LINKEDIN_LIVE_SUBMIT_DISABLED"] = "0"
        return {"status": "ok", "state": state}
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@mcp.tool()
def generate_tailored_resume_for_job(
    job_title: str,
    company: str,
    job_description: str,
    master_resume_path: str = "",
    target_ats_score: int = 85,
    max_iterations: int = 5,
) -> dict:
    """
    Generate a truthfully-optimized resume for a specific job using the ATS loop.
    Does NOT fabricate experience — stops at truth-safe ceiling.
    
    Returns resume_path, ats scores, keywords covered/missing, optimization_summary.
    """
    try:
        from services.resume_package_service import generate_package_for_job
        package = generate_package_for_job(
            job_title=job_title,
            company=company,
            job_description=job_description,
            master_resume_path=master_resume_path or None,
            target_ats_score=target_ats_score,
            max_iterations=max_iterations,
        )
        return {"status": "ok", **package}
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@mcp.tool()
def get_job_queue_for_review(
    jobs_json: str,
    master_resume_text: str = "",
    master_resume_path: str = "",
) -> dict:
    """
    Score a batch of discovered jobs using the structured fit engine.
    Returns a ready-to-review approval list grouped by:
      high_confidence_match | review_fit | skip
    
    jobs_json: JSON array of job objects with keys:
      url, title, company, description, location, work_type
    
    Adds each scored job to the apply_queue DB. Returns the queue summary.
    """
    try:
        import json as _json
        from services.fit_engine import score_structured_fit, fit_result_to_dict
        from services.job_prefilter import prefilter_batch
        from services.apply_queue_service import upsert_queue_item, get_queue_summary
        from services.profile_service import load_profile
        from services.resume_package_service import _load_master_resume_text
        from enhanced_ats_checker import EnhancedATSChecker

        jobs = _json.loads(jobs_json) if isinstance(jobs_json, str) else jobs_json
        if isinstance(jobs, dict) and "jobs" in jobs:
            jobs = jobs["jobs"]

        profile = load_profile() or {}
        resume_text = master_resume_text
        if not resume_text:
            resume_text = _load_master_resume_text(master_resume_path or None)

        ats_checker = EnhancedATSChecker()

        # Compute ATS scores
        ats_scores = {}
        for job in jobs:
            url = job.get("url", job.get("job_url", ""))
            title = job.get("title", job.get("job_title", ""))
            company = job.get("company", "")
            desc = job.get("description", job.get("job_description", ""))
            if url and desc and resume_text:
                try:
                    r = ats_checker.comprehensive_ats_check(
                        resume_text=resume_text,
                        job_description=desc,
                        job_title=title,
                        company_name=company,
                        location="",
                    )
                    ats_scores[url] = r.get("ats_score", 0)
                except Exception:
                    ats_scores[url] = 0

        # Prefilter
        result = prefilter_batch(jobs, resume_text=resume_text, profile=profile, ats_scores=ats_scores)

        job_lookup = {
            (j.get("url") or j.get("job_url") or ""): j
            for j in jobs
            if (j.get("url") or j.get("job_url"))
        }

        # Upsert into queue
        queued_ids = {}
        for category in ["high_confidence", "review_fit"]:
            for job_result in result[category]:
                url = job_result.get("job_url", "")
                if url:
                    job_meta = job_lookup.get(url, {})
                    item_id = upsert_queue_item(
                        job_url=url,
                        job_title=job_result.get("job_title", ""),
                        company=job_result.get("company", ""),
                        job_description=job_meta.get("description", job_meta.get("job_description", "")),
                        fit_data=job_result.get("fit", {}),
                        ats_score=ats_scores.get(url, 0),
                        truth_safe_ceiling=job_result.get("fit", {}).get("truth_safe_ats_ceiling", 0),
                        easy_apply_confirmed=bool(job_meta.get("easy_apply_confirmed", False)),
                    )
                    queued_ids[url] = item_id

        summary = get_queue_summary()

        return {
            "status": "ok",
            "high_confidence": result["high_confidence"],
            "review_fit": result["review_fit"],
            "skip": [{"job_url": j.get("job_url"), "company": j.get("company"),
                      "reason": j.get("reason")} for j in result["skip"]],
            "counts": {
                "high_confidence": result["high_confidence_count"],
                "review_fit": result["review_fit_count"],
                "skip": result["skip_count"],
                "total": result["total"],
            },
            "queue_summary": summary,
            "queued_ids": queued_ids,
        }
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e)[:300], "trace": traceback.format_exc()[-500:]}


def _normalize_job_input(job: dict) -> dict:
    j = job or {}
    url = (
        j.get("url")
        or j.get("job_url")
        or j.get("apply_url")
        or j.get("applyUrl")
        or ""
    )
    title = (
        j.get("title")
        or j.get("job_title")
        or j.get("jobTitle")
        or j.get("position")
        or ""
    )
    company = j.get("company") or j.get("company_name") or j.get("companyName") or ""
    description = j.get("description") or j.get("job_description") or ""
    location = j.get("location") or j.get("locationName") or ""
    work_type = j.get("work_type") or j.get("workType") or ""
    apply_url = j.get("apply_url") or j.get("applyUrl") or url
    return {
        "url": str(url or ""),
        "apply_url": str(apply_url or url or ""),
        "title": str(title or ""),
        "company": str(company or ""),
        "description": str(description or ""),
        "location": str(location or ""),
        "work_type": str(work_type or ""),
    }


def _answer_risk_summary(decision: dict) -> dict:
    answers = (decision or {}).get("answers") or {}
    counts = {"safe": 0, "review": 0, "missing": 0, "blocked": 0}
    risky_fields: list[str] = []
    for key, meta in answers.items():
        if not isinstance(meta, dict):
            continue
        ast = str(meta.get("answer_state") or "")
        if ast in counts:
            counts[ast] += 1
        if ast in ("review", "missing", "blocked"):
            risky_fields.append(str(key))
    return {
        "counts": counts,
        "risky_fields": risky_fields[:24],
        "critical_unsatisfied": list((decision or {}).get("critical_unsatisfied") or [])[:24],
        "safe_to_submit": bool(decision.get("safe_to_submit", False)),
    }


@mcp.tool()
def evaluate_job_and_prepare_action_plan(
    job_json: str,
    master_resume_text: str = "",
    master_resume_path: str = "",
    include_package: bool = True,
    target_ats_score: int = 85,
    max_iterations: int = 5,
    render_one_page_pdf: bool = False,
    template_id: str = "classic_ats",
) -> dict:
    """
    Orchestrate a single job through the full policy pipeline.

    Returns:
      - normalized_job
      - fit (structured fit result)
      - ats_score
      - job_state (policy decision)
      - answer_risk_summary
      - package_artifacts (when include_package=True)
      - next_action (recommended)
    """
    try:
        job = json.loads(job_json) if isinstance(job_json, str) else job_json
        normalized = _normalize_job_input(job if isinstance(job, dict) else {})

        from services.profile_service import load_profile
        from services.fit_engine import score_structured_fit, fit_result_to_dict
        from services.resume_package_service import _load_master_resume_text, generate_package_for_job
        from services.queue_transitions import determine_initial_state, determine_state_after_package, recommended_action
        from services.application_decision import build_application_decision

        profile = load_profile() or {}
        resume_text = master_resume_text or _load_master_resume_text(master_resume_path or None)

        fit = score_structured_fit(
            normalized.get("title", ""),
            normalized.get("description", ""),
            resume_text,
            profile,
        )
        fit_dict = fit_result_to_dict(fit)

        ats_score = 0
        try:
            from enhanced_ats_checker import EnhancedATSChecker

            if resume_text and normalized.get("description"):
                ats_checker = EnhancedATSChecker()
                ats = ats_checker.comprehensive_ats_check(
                    resume_text=resume_text,
                    job_description=normalized.get("description", ""),
                    job_title=normalized.get("title", ""),
                    company_name=normalized.get("company", ""),
                    location=normalized.get("location", ""),
                )
                ats_score = int(ats.get("ats_score", 0) or 0)
        except Exception:
            ats_score = 0

        decision_job = {
            "url": normalized.get("url", ""),
            "apply_url": normalized.get("apply_url", ""),
            "title": normalized.get("title", ""),
            "company": normalized.get("company", ""),
            "description": normalized.get("description", ""),
            "fit_decision": fit_dict.get("fit_decision", ""),
            "ats_score": ats_score,
            "unsupported_requirements": fit_dict.get("unsupported_requirements", []),
        }
        decision = build_application_decision(
            decision_job,
            profile=profile,
            master_resume_text=resume_text,
        )
        answer_risk = _answer_risk_summary(decision)

        queue_state = determine_initial_state(
            fit_decision=fit_dict.get("fit_decision", ""),
            overall_fit_score=int(fit_dict.get("overall_fit_score", 0) or 0),
            hard_blockers=fit_dict.get("hard_blockers") or [],
        )

        package: dict = {}
        package_status = "not_generated"
        if include_package:
            package = generate_package_for_job(
                job_title=normalized.get("title", ""),
                company=normalized.get("company", ""),
                job_description=normalized.get("description", ""),
                master_resume_path=master_resume_path or None,
                target_ats_score=target_ats_score,
                max_iterations=max_iterations,
                render_one_page_pdf=render_one_page_pdf,
                template_id=template_id,
            )
            package_status = str(package.get("package_status") or package_status)
            queue_state = determine_state_after_package(
                current_state=queue_state,
                fit_decision=fit_dict.get("fit_decision", ""),
                overall_fit_score=int(fit_dict.get("overall_fit_score", 0) or 0),
                package_status=package_status,
                hard_blockers=fit_dict.get("hard_blockers") or [],
                unsupported_requirements=fit_dict.get("unsupported_requirements") or [],
            )

        next_action = recommended_action(job_state=queue_state, package_status=package_status)

        return {
            "status": "ok",
            "normalized_job": normalized,
            "fit": fit_dict,
            "ats_score": ats_score,
            "job_state": decision.get("job_state", ""),
            "answer_risk_summary": answer_risk,
            "package_artifacts": package,
            "queue_state": queue_state,
            "next_action": next_action,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@mcp.tool()
def approve_jobs_for_apply(
    item_ids_json: str,
) -> dict:
    """
    Approve one or more queue items for automated applying.
    Only approved items will be processed by the apply runner.
    
    item_ids_json: JSON array of queue item IDs returned by get_job_queue_for_review.
    """
    try:
        import json as _json
        from services.approval_service import approve_job_with_metadata
        from services.apply_queue_service import get_item_by_id

        ids = _json.loads(item_ids_json) if isinstance(item_ids_json, str) else item_ids_json
        approved = []
        not_found = []

        for item_id in ids:
            item = get_item_by_id(item_id)
            if item:
                approve_job_with_metadata(item_id, approved_by="mcp")
                approved.append({
                    "id": item_id,
                    "job_title": item.get("job_title"),
                    "company": item.get("company"),
                })
            else:
                not_found.append(item_id)

        return {
            "status": "ok",
            "approved_count": len(approved),
            "approved": approved,
            "not_found": not_found,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@mcp.tool()
def run_approved_queue(
    dry_run: bool = False,
    max_jobs: int = 20,
    target_ats_score: float = 85.0,
    master_resume_path: str = "",
    skip_resume_generation: bool = False,
) -> dict:
    """
    Phase 10 — One-by-one queue runner.
    Processes only approved_for_apply items, enforcing approved resume bindings.

    For each job:
      1. Validate approved queue item + resume binding
      2. Run LinkedIn Easy Apply via apply_to_jobs_payload (one job at a time)
      3. Update runner_state + job_state

    dry_run=True: fill without submit (runner_state=stopped_review_required).
    max_jobs: Safety cap per single run (default 20).

    Returns per-job runner_state + job_state outcomes.
    """
    try:
        from services.runner_queue_executor import run_approved_queue as _run, RunnerConfig

        cfg = RunnerConfig(
            dry_run=dry_run,
            max_jobs=max_jobs,
            rate_limit_seconds=5.0,
            require_safeguards=True,
            manual_assist=False,
        )
        return _run(cfg)
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e)[:300], "trace": traceback.format_exc()[-500:]}


@mcp.tool()
def get_queue_status() -> dict:
    """
    Return current queue summary — counts by state, pending approvals, and recent activity.
    Use this to check what's in the queue before running apply.
    """
    try:
        from services.apply_queue_service import get_queue_summary, get_queue
        from services.apply_queue_service import JobQueueState

        summary = get_queue_summary()
        pending_approval = get_queue(
            states=[JobQueueState.READY_FOR_APPROVAL, JobQueueState.REVIEW_FIT],
            limit=50,
        )
        approved = get_queue(states=[JobQueueState.APPROVED_FOR_APPLY], limit=50)
        recently_applied = get_queue(states=[JobQueueState.APPLIED], limit=10)

        return {
            "status": "ok",
            "summary": summary,
            "pending_user_approval": [
                {
                    "id": i["id"],
                    "job_title": i.get("job_title"),
                    "company": i.get("company"),
                    "job_state": i.get("job_state"),
                    "fit_score": i.get("fit_score"),
                    "ats_score": i.get("ats_score"),
                }
                for i in pending_approval
            ],
            "approved_ready_to_apply": [
                {
                    "id": i["id"],
                    "job_title": i.get("job_title"),
                    "company": i.get("company"),
                    "package_status": i.get("package_status"),
                    "ats_score": i.get("ats_score"),
                }
                for i in approved
            ],
            "recently_applied": [
                {
                    "id": i["id"],
                    "job_title": i.get("job_title"),
                    "company": i.get("company"),
                    "applied_at": i.get("applied_at"),
                }
                for i in recently_applied
            ],
        }
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


if __name__ == "__main__":
    # Run with: python -m mcp_servers.job_apply_autofill.server
    # Or: fastmcp run mcp_servers/job_apply_autofill/server.py
    try:
        mcp.run()
    except TypeError:
        mcp.run(transport="stdio")
