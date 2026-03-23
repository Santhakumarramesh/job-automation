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
        from agents.application_answerer import answer_question

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
            "work_authorization": profile.get("work_authorization_note", "") or "Authorized to work. No sponsorship required.",
            "relocation": profile.get("relocation_preference", ""),
            "salary": profile.get("salary_expectation_rule", "Negotiable"),
            "availability": profile.get("notice_period", "Immediate") or "Immediate",
        }

        if question_hints:
            hints = [h.strip() for h in question_hints.split(",") if h.strip()]
            job_ctx = {"company": "", "title": ""}
            for hint in hints:
                ans = answer_question(hint, profile=profile, job_context=job_ctx)
                if ans:
                    values[f"q_{hint[:30]}"] = ans[:150]

        return {"status": "ok", "values": values}
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
    jobs_json: JSON string, list of {title, company, url, easy_apply?, fit_decision?, ats_score?, unsupported_requirements?}.
    dry_run: if True, fill forms but do not submit. Recommended for first run.
    rate_limit_seconds: min seconds between applications (default 90).
    manual_assist: if True, allow external ATS (Greenhouse, Lever, Workday). Default False = Easy Apply only.
    require_safeguards: if True, skip jobs without fit_decision=Apply and ats_score>=85 when provided.
    Requires LINKEDIN_EMAIL, LINKEDIN_PASSWORD. Resume from Master_Resumes or RESUME_PATH.
    """
    try:
        from playwright.async_api import async_playwright
        from agents.application_runner import RunConfig, RunResult, run_application, save_run_results

        from services.profile_service import load_profile
        from application_tracker import log_application_from_result
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

    # Filter: when not manual_assist, only LinkedIn Easy Apply
    if not manual_assist:
        filtered = []
        for j in jobs:
            jdict = j if isinstance(j, dict) else {}
            url = str(jdict.get("url") or jdict.get("applyUrl") or "")
            if "linkedin.com" not in url.lower():
                continue
            if not jdict.get("easy_apply", jdict.get("easyApply", False)):
                continue
            filtered.append(j)
        if not filtered:
            return {"status": "error", "message": "No Easy Apply jobs in JSON. Set manual_assist=True for external ATS, or export Easy Apply jobs only."}
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
                return {"status": "error", "message": "LinkedIn verification required. Complete login manually, then retry."}
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
                })
                if result.status == "applied":
                    applied += 1
                    try:
                        log_application_from_result(result, resume_path=config.resume_path or "")
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


if __name__ == "__main__":
    # Run with: python -m mcp_servers.job_apply_autofill.server
    # Or: fastmcp run mcp_servers/job_apply_autofill/server.py
    try:
        mcp.run()
    except TypeError:
        mcp.run(transport="stdio")
