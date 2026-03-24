#!/usr/bin/env python3
"""
Job Apply Autofill MCP Server

Exposes tools for quick job application autofill (JobRight-style):
- LinkedIn Easy Apply (primary)
- Greenhouse, Lever, Workday, and other external ATS (redirects from LinkedIn)

Resume is renamed per job: {Name}_{Position}_at_{Company}_Resume.pdf

Requires: pip install fastmcp playwright mcp
Then: playwright install chromium
"""

import asyncio
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

mcp = FastMCP(
    "job_apply_autofill",
    description="Autofill job applications on LinkedIn Easy Apply and external ATS (Greenhouse, Lever, Workday). Resume renamed per job.",
)


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
        from services.resume_naming import resume_path_for_job, ensure_resume_exists_for_job

        job = {"title": job_title, "company": company}
        path = ensure_resume_exists_for_job(
            job,
            resume_content_path=resume_source_path or os.getenv("RESUME_PATH"),
            output_dir=str(PROJECT_ROOT / "generated_resumes"),
        )
        if path:
            return {"resume_path": path, "filename": os.path.basename(path), "status": "ready"}
        return {"resume_path": "", "filename": "", "status": "no_source", "message": "No resume found. Add PDF to Master_Resumes/ or set RESUME_PATH."}
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
        from services.profile_service import load_profile
        from agents.application_answerer import answer_question_structured

        profile = load_profile()
        if not profile:
            return {"status": "no_profile", "message": "Copy config/candidate_profile.example.json to candidate_profile.json"}

        values = {
            "first_name": (profile.get("full_name", "") or "").split()[0] or "",
            "last_name": " ".join((profile.get("full_name", "") or "").split()[1:]) or (profile.get("full_name", "") or "").split()[0] or "",
            "email": profile.get("email", "") or os.getenv("LINKEDIN_EMAIL", ""),
            "phone": profile.get("phone", "") or os.getenv("PHONE", ""),
            "linkedin_url": profile.get("linkedin_url", ""),
            "github_url": profile.get("github_url", ""),
            "portfolio_url": profile.get("portfolio_url", ""),
            "work_authorization": profile.get("work_authorization_note", "") or "",
            "relocation": profile.get("relocation_preference", ""),
            "salary": profile.get("salary_expectation_rule", "Negotiable"),
            "availability": profile.get("notice_period", "Immediate") or "Immediate",
        }

        review_flags: dict = {}
        if question_hints:
            hints = [h.strip() for h in question_hints.split(",") if h.strip()]
            job_ctx = {"company": "", "title": ""}
            for hint in hints:
                meta = answer_question_structured(hint, profile=profile, job_context=job_ctx)
                key = f"q_{hint[:30]}"
                if meta["answer"]:
                    values[key] = meta["answer"][:150]
                review_flags[key] = {
                    "manual_review_required": meta["manual_review_required"],
                    "reason_codes": meta["reason_codes"],
                    "classified_type": meta["classified_type"],
                }

        return {"status": "ok", "values": values, "answer_review": review_flags}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}


@mcp.tool()
def apply_to_jobs(
    jobs_json: str,
    dry_run: bool = False,
    rate_limit_seconds: float = 90.0,
    manual_assist: bool = False,
    require_safeguards: bool = True,
) -> dict:
    """
    Apply to jobs from JSON. By default: Easy Apply only, no external ATS.
    jobs_json: JSON string, list of {title, company, url, easy_apply?, easy_apply_confirmed?, apply_mode?, fit_decision?, ats_score?, unsupported_requirements?}.
    dry_run: if True, fill forms but do not submit. Recommended for first run.
    rate_limit_seconds: min seconds between applications (default 90).
    manual_assist: if True, allow external ATS (Greenhouse, Lever, Workday). Default False = Easy Apply only.
    require_safeguards: if True, skip jobs without fit_decision=Apply and ats_score>=85 when provided.
    Requires LINKEDIN_EMAIL, LINKEDIN_PASSWORD. Resume from Master_Resumes or RESUME_PATH.
    """
    try:
        from playwright.async_api import async_playwright
        from agents.application_runner import (
            RunConfig,
            RunResult,
            answerer_review_pending,
            run_application,
            save_run_results,
        )

        from services.profile_service import load_profile
        from services.application_tracker import log_application_from_result
    except ImportError as e:
        return {"status": "error", "message": f"Import failed: {e}. Install: pip install playwright mcp && playwright install chromium"}

    try:
        jobs = json.loads(jobs_json)
        if not isinstance(jobs, list):
            jobs = jobs.get("jobs", []) or []
    except json.JSONDecodeError as e:
        return {"status": "error", "message": f"Invalid JSON: {e}"}

    if not jobs:
        return {"status": "error", "message": "No jobs in JSON"}

    # Filter: when not manual_assist, only LinkedIn Easy Apply with easy_apply_confirmed
    if not manual_assist:
        filtered = []
        for j in jobs:
            jdict = j if isinstance(j, dict) else {}
            url = str(jdict.get("url") or jdict.get("applyUrl") or "")
            if "linkedin.com" not in url.lower():
                continue
            if not jdict.get("easy_apply_confirmed", False):
                continue
            apply_mode = jdict.get("apply_mode", "")
            if apply_mode == "skip":
                continue
            filtered.append(j)
        if not filtered:
            return {"status": "error", "message": "No Easy Apply jobs (easy_apply_confirmed=True) in JSON. Set manual_assist=True for external ATS, or export confirmed Easy Apply jobs only."}
        jobs = filtered

    # Filter: require_safeguards - skip jobs that don't meet fit/ATS bar when metadata present
    if require_safeguards:
        filtered = []
        for j in jobs:
            jdict = j if isinstance(j, dict) else {}
            fit = jdict.get("fit_decision", "")
            ats = jdict.get("ats_score")
            unsup = jdict.get("unsupported_requirements", [])
            if not fit and ats is None:
                filtered.append(j)  # No metadata: allow (UI didn't provide)
            elif fit and fit.lower() != "apply":
                continue  # Skip: fit not Apply
            elif ats is not None and int(ats) < 85:
                continue  # Skip: ATS below threshold
            elif unsup and len(unsup) > 0:
                continue  # Skip: has unsupported requirements
            else:
                filtered.append(j)
        jobs = filtered
        if not jobs:
            return {"status": "error", "message": "No jobs pass safeguards (fit_decision=Apply, ats_score>=85, no unsupported)."}

    try:
        profile = load_profile()
    except Exception:
        profile = {}

    resume_path = os.getenv("RESUME_PATH")
    if not resume_path or not os.path.isfile(resume_path):
        for base in [PROJECT_ROOT / "Master_Resumes", PROJECT_ROOT / "generated_resumes"]:
            if base.exists():
                for f in base.rglob("*.pdf"):
                    resume_path = str(f)
                    break
            if resume_path:
                break

    config = RunConfig(
        resume_path=resume_path or "",
        profile=profile,
        dry_run=dry_run,
        rate_limit_sec=rate_limit_seconds,
        confirm_before_submit=not dry_run,
        screenshots_dir=str(PROJECT_ROOT / "application_runs" / "screenshots"),
        use_answerer=True,
        easy_apply_only=not manual_assist,
    )

    email = os.getenv("LINKEDIN_EMAIL") or os.getenv("EMAIL")
    password = os.getenv("LINKEDIN_PASSWORD")
    if not email or not password:
        return {"status": "error", "message": "Set LINKEDIN_EMAIL and LINKEDIN_PASSWORD"}

    async def _run():
        import random

        results = []
        run_results = []
        applied = 0
        screenshot_dir = PROJECT_ROOT / "application_runs" / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            await page.goto("https://www.linkedin.com/login", wait_until="networkidle", timeout=30000)
            await page.fill('input[name="session_key"]', email)
            await page.wait_for_timeout(random.randint(300, 800))
            await page.fill('input[name="session_password"]', password)
            await page.wait_for_timeout(random.randint(400, 1000))
            await page.click('button[type="submit"]')
            await page.wait_for_load_state("networkidle", timeout=15000)
            if "checkpoint" in page.url or "challenge" in page.url:
                await browser.close()
                return {
                    "status": "error",
                    "message": "LinkedIn verification required. Complete login manually in a browser (https://linkedin.com), then retry. See docs/setup/job-apply-autofill-mcp.md for troubleshooting.",
                }
            await page.wait_for_timeout(2000)

            for i, job in enumerate(jobs):
                await asyncio.sleep(random.uniform(max(5, rate_limit_seconds / 6), max(10, rate_limit_seconds / 4)))
                j = job if isinstance(job, dict) else {}
                url = j.get("url") or j.get("applyUrl") or ""
                if not url:
                    rr = RunResult(status="skipped", company=j.get("company", ""), position=j.get("title", ""), job_url="", error="no_url")
                    run_results.append(rr)
                    results.append({"company": j.get("company", ""), "status": "skipped", "reason": "no_url"})
                    continue
                result = await run_application(page, j, config, screenshot_dir=screenshot_dir)
                run_results.append(result)
                results.append({
                    "company": result.company,
                    "position": result.position,
                    "status": result.status,
                    "error": result.error or "",
                    "answerer_manual_review_required": answerer_review_pending(result.answerer_review),
                    "answerer_review_field_keys": list((result.answerer_review or {}).keys())[:12],
                })
                if result.status == "applied":
                    applied += 1
                    try:
                        from services.policy_service import policy_from_exported_job

                        mode, reason = policy_from_exported_job(j)
                        meta = {
                            "job_id": j.get("job_id", ""),
                            "fit_decision": j.get("fit_decision", ""),
                            "ats_score": j.get("ats_score", j.get("final_ats_score")),
                            "apply_mode": mode,
                            "policy_reason": reason,
                            "easy_apply_confirmed": j.get("easy_apply_confirmed"),
                            "description": j.get("description", "")[:2000],
                        }
                        log_application_from_result(result, resume_path=config.resume_path or "", job_metadata=meta)
                    except Exception:
                        pass

            await browser.close()

        save_path = save_run_results(run_results)
        return {
            "status": "ok",
            "applied": applied,
            "total": len(jobs),
            "results": results,
            "results_file": save_path,
        }

    try:
        out = asyncio.run(_run())
        return out
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@mcp.tool()
def detect_form_type(url: str) -> dict:
    """
    Detect application form type from URL.
    Returns: linkedin, greenhouse, lever, workday, or generic.
    """
    try:
        from agents.application_runner import detect_form_type as _detect

        ft = _detect(url)
        return {"url": url, "form_type": ft}
    except Exception as e:
        return {"url": url, "form_type": "generic", "error": str(e)[:100]}


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
    job_json: JSON object with url, easy_apply_confirmed.
    Returns apply_mode and reason.
    """
    try:
        from services.policy_service import decide_apply_mode_with_reason as _decide_wr
        from services.profile_service import load_profile, is_auto_apply_ready

        job = json.loads(job_json) if isinstance(job_json, str) else (job_json or {})
        ats = int(ats_score) if ats_score and str(ats_score).strip() else None
        unsup = json.loads(unsupported_requirements_json) if isinstance(unsupported_requirements_json, str) else []
        profile_ready = is_auto_apply_ready(load_profile())
        mode, reason = _decide_wr(
            job, fit_decision or "", ats, unsup, profile_ready=profile_ready
        )
        return {"apply_mode": mode, "policy_reason": reason, "status": "ok"}
    except Exception as e:
        return {"apply_mode": "manual_assist", "policy_reason": "error", "status": "error", "message": str(e)[:150]}


@mcp.tool()
def validate_candidate_profile(profile_path: str = "") -> dict:
    """
    Validate candidate profile. Checks full_name, email, phone, linkedin_url,
    github_url, portfolio_url, work_authorization_note, notice_period, short_answers.
    Returns warnings, auto_apply_ready, and suggested fixes.
    """
    try:
        from services.profile_service import load_profile, validate_profile, is_auto_apply_ready

        profile = load_profile(profile_path or None)
        if not profile:
            return {
                "status": "no_profile",
                "auto_apply_ready": False,
                "warnings": ["No profile found. Copy config/candidate_profile.example.json to candidate_profile.json"],
                "suggested_fixes": ["Create config/candidate_profile.json with full_name, email, phone, linkedin_url, work_authorization_note, notice_period"],
            }
        warnings = validate_profile(profile)
        short = profile.get("short_answers", {}) or {}
        for k in ["sponsorship", "why_this_role", "why_this_company", "availability"]:
            if not short.get(k) or not str(short.get(k)).strip():
                warnings.append(f"short_answers.{k} is empty")
        auto_ready = is_auto_apply_ready(profile)
        suggested = []
        for k in ["full_name", "email", "phone", "linkedin_url", "work_authorization_note", "notice_period"]:
            if not profile.get(k) or not str(profile.get(k)).strip():
                suggested.append(f"Add {k}")
        return {
            "status": "ok",
            "auto_apply_ready": auto_ready,
            "warnings": warnings,
            "suggested_fixes": suggested[:10],
        }
    except Exception as e:
        return {"status": "error", "auto_apply_ready": False, "message": str(e)[:200]}


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
        from services.ats_service import check_fit_gate
        from enhanced_ats_checker import EnhancedATSChecker

        state = {
            "base_resume_text": master_resume_text,
            "job_description": job_description,
            "target_position": job_title or "Role",
            "target_company": company or "Company",
            "target_location": location or "USA",
        }
        fit_result = check_fit_gate(state)
        checker = EnhancedATSChecker()
        ats_results = checker.comprehensive_ats_check(
            resume_text=master_resume_text,
            job_description=job_description,
            job_title=job_title or "Role",
            company_name=company or "Company",
            location=location or "USA",
            target_truthful_score=100,
            master_resume_text=master_resume_text,
        )
        missing = ats_results.get("detailed_breakdown", {}).get("missing_keywords", [])
        merged_unsup = sorted(
            {
                str(x).strip()
                for x in (fit_result.get("unsupported_requirements") or [])
                + (ats_results.get("unsupported_requirements") or [])
                if str(x).strip()
            }
        )
        from services.truth_safe_ats import compute_truth_safe_ats_ceiling

        truthful_left = ats_results.get("truthful_missing_keywords") or []
        ceiling = compute_truth_safe_ats_ceiling(
            final_ats_score=ats_results.get("ats_score", 0),
            target_score=100,
            truth_safe=True,
            converged=int(ats_results.get("ats_score", 0) or 0) >= 100,
            no_truthful_improvement=not bool(truthful_left),
            unsupported_requirements=merged_unsup,
            truthful_missing_keywords=truthful_left,
        )
        return {
            "status": "ok",
            "fit_score": fit_result.get("job_fit_score", 0),
            "fit_decision": fit_result.get("fit_decision", "Review"),
            "ats_score": ats_results.get("ats_score", 0),
            "missing_keywords": missing[:15],
            "unsupported_requirements": merged_unsup[:10] or fit_result.get("unsupported_requirements", [])[:10],
            "ats_feasible": ats_results.get("ats_score", 0) >= 85,
            "truth_safe_ats_ceiling": ceiling["truth_safe_ats_ceiling"],
            "truth_safe_ceiling_reason": ceiling["truth_safe_ceiling_reason"],
        }
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}


@mcp.tool()
def confirm_easy_apply(job_url: str) -> dict:
    """
    Open job page (after LinkedIn login) and confirm Easy Apply button exists.
    Returns easy_apply_confirmed. Requires LINKEDIN_EMAIL, LINKEDIN_PASSWORD.
    """
    if not job_url or "linkedin.com" not in str(job_url).lower():
        return {"easy_apply_confirmed": False, "status": "error", "message": "URL must be a LinkedIn job URL"}
    try:
        from playwright.async_api import async_playwright
        import random

        email = os.getenv("LINKEDIN_EMAIL") or os.getenv("EMAIL")
        password = os.getenv("LINKEDIN_PASSWORD")
        if not email or not password:
            return {"easy_apply_confirmed": False, "status": "error", "message": "Set LINKEDIN_EMAIL and LINKEDIN_PASSWORD"}

        async def _check():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
                )
                page = await context.new_page()
                await page.goto("https://www.linkedin.com/login", wait_until="networkidle", timeout=30000)
                await page.fill('input[name="session_key"]', email)
                await page.wait_for_timeout(random.randint(300, 600))
                await page.fill('input[name="session_password"]', password)
                await page.click('button[type="submit"]')
                await page.wait_for_load_state("networkidle", timeout=15000)
                if "checkpoint" in page.url or "challenge" in page.url:
                    await browser.close()
                    return False, "login_challenge"
                await page.wait_for_timeout(1500)
                await page.goto(job_url, wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(2000)
                found = False
                for sel in [
                    "button[aria-label*='Easy Apply']",
                    "button:has-text('Easy Apply')",
                    "button:has-text('Apply now')",
                    "[data-control-name='apply_from_job_card']",
                ]:
                    btn = await page.query_selector(sel)
                    if btn and await btn.is_visible():
                        found = True
                        break
                await browser.close()
                return found, None

        found, err = asyncio.run(_check())
        if err == "login_challenge":
            return {"easy_apply_confirmed": False, "status": "login_challenge", "message": "LinkedIn verification required. Complete login manually, then retry."}
        return {"easy_apply_confirmed": found, "status": "ok", "url": job_url}
    except Exception as e:
        return {"easy_apply_confirmed": False, "status": "error", "message": str(e)[:200]}


# --- Execution tools ---

@mcp.tool()
def prepare_application_package(
    job_title: str,
    company: str,
    job_description: str = "",
    master_resume_text: str = "",
) -> dict:
    """
    Prepare full application package for manual-assist lane: job-specific resume path,
    cover letter path (if generated), autofill values, short answers, fit decision, ATS score.
    """
    try:
        from services.resume_naming import ensure_resume_exists_for_job
        from services.profile_service import load_profile
        from agents.application_answerer import answer_question_structured

        job = {"title": job_title, "company": company, "description": job_description}
        resume_path = ensure_resume_exists_for_job(
            job,
            resume_content_path=os.getenv("RESUME_PATH"),
            output_dir=str(PROJECT_ROOT / "generated_resumes"),
        )
        profile = load_profile()
        jc = {"company": company, "title": job_title}
        sp = answer_question_structured("Do you require sponsorship?", profile=profile, job_context=jc)
        wr = answer_question_structured("Why this role?", profile=profile, job_context=jc)
        wc = answer_question_structured("Why this company?", profile=profile, job_context=jc)
        values = {
            "first_name": (profile.get("full_name", "") or "").split()[0] or "",
            "last_name": " ".join((profile.get("full_name", "") or "").split()[1:]) or "",
            "email": profile.get("email", ""),
            "phone": profile.get("phone", ""),
            "linkedin_url": profile.get("linkedin_url", ""),
            "github_url": profile.get("github_url", ""),
            "work_authorization": profile.get("work_authorization_note", ""),
            "sponsorship": sp["answer"],
            "why_this_role": wr["answer"],
            "why_this_company": wc["answer"],
        }
        answer_review = {
            "sponsorship": {
                "manual_review_required": sp["manual_review_required"],
                "reason_codes": sp["reason_codes"],
                "classified_type": sp["classified_type"],
            },
            "why_this_role": {
                "manual_review_required": wr["manual_review_required"],
                "reason_codes": wr["reason_codes"],
                "classified_type": wr["classified_type"],
            },
            "why_this_company": {
                "manual_review_required": wc["manual_review_required"],
                "reason_codes": wc["reason_codes"],
                "classified_type": wc["classified_type"],
            },
        }
        fit_result = {}
        if job_description and master_resume_text:
            from services.ats_service import check_fit_gate
            state = {"base_resume_text": master_resume_text, "job_description": job_description, "target_position": job_title, "target_company": company, "target_location": "USA"}
            fit_result = check_fit_gate(state)
        return {
            "status": "ok",
            "resume_path": resume_path or "",
            "autofill_values": values,
            "answer_review": answer_review,
            "fit_decision": fit_result.get("fit_decision", ""),
            "job_fit_score": fit_result.get("job_fit_score", 0),
            "unsupported_requirements": fit_result.get("unsupported_requirements", []),
        }
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
        path = Path(run_results_path)
        if not path.is_file():
            return {"status": "error", "message": f"File not found: {run_results_path}"}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            data = [data]
        all_unmapped = []
        for r in data:
            unmapped = r.get("unmapped_fields", [])
            if unmapped:
                all_unmapped.extend(unmapped)
        from collections import Counter
        counts = Counter(all_unmapped)
        suggestions = []
        key_hints = {"sponsor": "short_answers.sponsorship", "salary": "salary_expectation_rule", "phone": "phone", "relocat": "relocation_preference", "years": "short_answers.years_*", "why": "short_answers.why_this_role"}
        for field, _ in counts.most_common(15):
            f_lower = (field or "").lower()
            for kw, prof_key in key_hints.items():
                if kw in f_lower:
                    suggestions.append(f"{field} → add {prof_key}")
                    break
        return {
            "status": "ok",
            "unmapped_summary": dict(counts),
            "total_unmapped": len(all_unmapped),
            "suggested_profile_keys": suggestions[:10],
        }
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
        jobs = json.loads(jobs_json) if isinstance(jobs_json, str) else jobs_json
        if not isinstance(jobs, list) or not jobs:
            return {"status": "error", "message": "jobs_json must be a non-empty list"}
        from services.ats_service import check_fit_gate
        from enhanced_ats_checker import EnhancedATSChecker

        scored = []
        for i, j in enumerate(jobs[:max_scored]):
            j = j if isinstance(j, dict) else {}
            jd = j.get("description", "") or j.get("job_details", "")
            if not jd or len(jd) < 100:
                scored.append({**j, "fit_score": 0, "fit_decision": "Review", "ats_score": 0, "priority_note": "No JD"})
                continue
            state = {
                "base_resume_text": master_resume_text,
                "job_description": jd,
                "target_position": j.get("title", ""),
                "target_company": j.get("company", ""),
                "target_location": "USA",
            }
            fit = check_fit_gate(state)
            checker = EnhancedATSChecker()
            ats = checker.comprehensive_ats_check(
                resume_text=master_resume_text, job_description=jd,
                job_title=j.get("title", ""), company_name=j.get("company", ""),
                location="USA", target_truthful_score=100, master_resume_text=master_resume_text,
            )
            scored.append({
                "title": j.get("title"),
                "company": j.get("company"),
                "url": j.get("url"),
                "easy_apply_confirmed": j.get("easy_apply_confirmed", False),
                "fit_score": fit.get("job_fit_score", 0),
                "fit_decision": fit.get("fit_decision", "Review"),
                "ats_score": ats.get("ats_score", 0),
            })
        scored.sort(key=lambda x: (
            -(x.get("easy_apply_confirmed") or False),
            -x.get("fit_score", 0),
            -x.get("ats_score", 0),
        ))
        return {"status": "ok", "prioritized": scored}
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
        from services.profile_service import load_profile
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import SystemMessage, HumanMessage

        profile = load_profile()
        name = profile.get("full_name", "Candidate")
        date = application_date or "recently"
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.5)
        prompt = f"""Generate two brief professional follow-ups for a job applicant.
- Applicant: {name}
- Role: {job_title} at {company}
- Applied: {date}

1. LinkedIn message (2-3 sentences, max 200 chars): polite, reference the role, express continued interest.
2. Email subject + body (2-3 sentences): similar tone, professional.

Return as JSON: {{"linkedin_message": "...", "email_subject": "...", "email_body": "..."}}
"""
        r = llm.invoke([HumanMessage(content=prompt)])
        import re
        text = (r.content or "").strip()
        m = re.search(r'\{[\s\S]*\}', text)
        try:
            data = json.loads(m.group(0)) if m else {}
        except json.JSONDecodeError:
            data = {}
        data.setdefault("linkedin_message", text[:200] if text else "")
        data.setdefault("email_subject", f"Following up - {job_title}")
        data.setdefault("email_body", text[:300] if text else "")
        return {"status": "ok", **data}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}


@mcp.tool()
def application_audit_report(run_results_path: str) -> dict:
    """
    After a batch run, return applied count, skipped count, fail reasons,
    unmapped fields summary, profile gaps, next recommended fixes.
    """
    try:
        path = Path(run_results_path)
        if not path.is_file():
            return {"status": "error", "message": f"File not found: {run_results_path}"}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            data = [data]
        applied = sum(1 for r in data if r.get("status") == "applied")
        skipped = sum(1 for r in data if r.get("status") == "skipped")
        failed = sum(1 for r in data if r.get("status") == "failed")
        dry_run = sum(1 for r in data if r.get("status") == "dry_run")
        manual = sum(1 for r in data if r.get("status") == "manual_assist_ready")
        errors = [r.get("error", "") for r in data if r.get("error")]
        all_unmapped = []
        for r in data:
            all_unmapped.extend(r.get("unmapped_fields", []) or [])
        from collections import Counter
        return {
            "status": "ok",
            "applied": applied,
            "skipped": skipped,
            "failed": failed,
            "dry_run": dry_run,
            "manual_assist_ready": manual,
            "fail_reasons": list(dict.fromkeys(e for e in errors if e))[:5],
            "unmapped_fields_count": len(all_unmapped),
            "unmapped_summary": dict(Counter(all_unmapped)),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}


if __name__ == "__main__":
    # Run with: python -m mcp_servers.job_apply_autofill.server
    # Or: fastmcp run mcp_servers/job_apply_autofill/server.py
    try:
        mcp.run()
    except TypeError:
        mcp.run(transport="stdio")
