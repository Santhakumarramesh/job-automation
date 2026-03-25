#!/usr/bin/env python3
"""
Career Copilot MCP — job application automation server.

Exposes tools for quick job application autofill (JobRight-style):
- LinkedIn Easy Apply (primary)
- Greenhouse, Lever, Workday, and other external ATS (redirects from LinkedIn)

Resume is renamed per job: {Name}_{Position}_at_{Company}_Resume.pdf

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
    "Career Copilot MCP — autofill job applications on LinkedIn Easy Apply and external ATS "
    "(Greenhouse, Lever, Workday). Resume renamed per job."
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
    jobs_json: JSON string, list of {title, company, url, easy_apply?, easy_apply_confirmed?, apply_mode?, fit_decision?, ats_score?, unsupported_requirements?}.
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


if __name__ == "__main__":
    # Run with: python -m mcp_servers.job_apply_autofill.server
    # Or: fastmcp run mcp_servers/job_apply_autofill/server.py
    try:
        mcp.run()
    except TypeError:
        mcp.run(transport="stdio")
