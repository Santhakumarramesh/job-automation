"""
LinkedIn headless flows: Easy Apply confirmation and batch apply (MCP parity).

Used by the job-apply MCP server and optionally by the REST API when gated.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


def _default_project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def confirm_easy_apply_payload(job_url: str) -> dict:
    """
    Open job page after LinkedIn login and confirm Easy Apply button exists.
    """
    if not job_url or "linkedin.com" not in str(job_url).lower():
        return {"easy_apply_confirmed": False, "status": "error", "message": "URL must be a LinkedIn job URL"}
    try:
        from providers.job_source import is_linkedin_jobs_listing_url

        if not is_linkedin_jobs_listing_url(str(job_url)):
            return {
                "easy_apply_confirmed": False,
                "status": "error",
                "message": "Use a LinkedIn job listing URL (path must include /jobs/), not a profile or company page.",
            }
    except Exception:
        pass

    try:
        from playwright.async_api import async_playwright

        from services.linkedin_easy_apply import find_visible_easy_apply_button
    except ImportError as e:
        return {
            "easy_apply_confirmed": False,
            "status": "error",
            "message": f"Import failed: {e}. Install: pip install playwright && playwright install chromium",
        }

    email = os.getenv("LINKEDIN_EMAIL") or os.getenv("EMAIL")
    password = os.getenv("LINKEDIN_PASSWORD")
    if not email or not password:
        return {"easy_apply_confirmed": False, "status": "error", "message": "Set LINKEDIN_EMAIL and LINKEDIN_PASSWORD"}

    async def _check():
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )
            page = await context.new_page()
            await page.goto("https://www.linkedin.com/login", wait_until="networkidle", timeout=30000)
            await page.fill('input[name="session_key"]', email)
            await page.wait_for_timeout(random.randint(300, 600))
            await page.fill('input[name="session_password"]', password)
            await page.click('button[type="submit"]')
            await page.wait_for_load_state("networkidle", timeout=15000)
            if "checkpoint" in page.url or "challenge" in page.url:
                try:
                    from services.apply_runner_metrics_redis import incr_apply_runner_event

                    incr_apply_runner_event("linkedin_login_challenge_abort")
                except ImportError:
                    pass
                await browser.close()
                return False, "login_challenge", None, []
            await page.wait_for_timeout(1500)
            await page.goto(job_url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)
            found, matched, tried = await find_visible_easy_apply_button(page)
            await browser.close()
            return found, None, matched, tried

    try:
        found, err, matched_sel, selectors_tried = asyncio.run(_check())
    except Exception as e:
        return {"easy_apply_confirmed": False, "status": "error", "message": str(e)[:200]}

    if err == "login_challenge":
        return {
            "easy_apply_confirmed": False,
            "status": "login_challenge",
            "message": "LinkedIn verification required. Complete login manually, then retry.",
        }
    out = {
        "easy_apply_confirmed": found,
        "status": "ok",
        "url": job_url,
        "matched_selector": matched_sel or "",
        "selectors_tried": selectors_tried or [],
    }
    if not found:
        out["message"] = "No Easy Apply control matched; page layout may have changed or job uses off-site apply."
    return out


def apply_to_jobs_payload(
    jobs: Union[str, List[Any]],
    *,
    dry_run: bool = False,
    rate_limit_seconds: float = 90.0,
    manual_assist: bool = False,
    require_safeguards: bool = True,
    project_root: Optional[Path] = None,
) -> dict:
    """
    Parse ``jobs`` (JSON string or list), filter, then run Playwright apply loop.
    """
    root = project_root or _default_project_root()

    try:
        from playwright.async_api import async_playwright
        from agents.application_runner import (
            RunConfig,
            RunResult,
            answerer_review_pending,
            run_application,
            save_run_results,
        )

        from services.application_tracker import log_runner_result_to_tracker
        from services.profile_service import load_profile
    except ImportError as e:
        return {"status": "error", "message": f"Import failed: {e}. Install: pip install playwright mcp && playwright install chromium"}

    if isinstance(jobs, str):
        try:
            jobs = json.loads(jobs)
        except json.JSONDecodeError as e:
            return {"status": "error", "message": f"Invalid JSON: {e}"}

    if isinstance(jobs, dict):
        jobs = jobs.get("jobs") or []
        if not isinstance(jobs, list):
            return {"status": "error", "message": 'jobs must be a list or JSON object with a "jobs" array'}
    elif not isinstance(jobs, list):
        return {"status": "error", "message": 'jobs must be a list or JSON object with a "jobs" array'}

    if not jobs:
        return {"status": "error", "message": "No jobs in JSON"}

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
            return {
                "status": "error",
                "message": "No Easy Apply jobs (easy_apply_confirmed=True) in JSON. Set manual_assist=True for external ATS, or export confirmed Easy Apply jobs only.",
            }
        jobs = filtered

    if require_safeguards:
        filtered = []
        for j in jobs:
            jdict = j if isinstance(j, dict) else {}
            fit = jdict.get("fit_decision", "")
            ats = jdict.get("ats_score")
            unsup = jdict.get("unsupported_requirements", [])
            if not fit and ats is None:
                filtered.append(j)
            elif fit and fit.lower() != "apply":
                continue
            elif ats is not None and int(ats) < 85:
                continue
            elif unsup and len(unsup) > 0:
                continue
            else:
                filtered.append(j)
        jobs = filtered
        if not jobs:
            return {
                "status": "error",
                "message": "No jobs pass safeguards (fit_decision=apply, ats_score>=85, no unsupported).",
            }

    try:
        profile = load_profile()
    except Exception:
        profile = {}

    resume_path = os.getenv("RESUME_PATH")
    if not resume_path or not os.path.isfile(resume_path):
        for base in [root / "Master_Resumes", root / "generated_resumes"]:
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
        screenshots_dir=str(root / "application_runs" / "screenshots"),
        use_answerer=True,
        easy_apply_only=not manual_assist,
    )

    email = os.getenv("LINKEDIN_EMAIL") or os.getenv("EMAIL")
    password = os.getenv("LINKEDIN_PASSWORD")
    if not email or not password:
        return {"status": "error", "message": "Set LINKEDIN_EMAIL and LINKEDIN_PASSWORD"}

    async def _run():
        results = []
        run_results = []
        applied = 0
        screenshot_dir = root / "application_runs" / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
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
                try:
                    from services.apply_runner_metrics_redis import incr_apply_runner_event

                    incr_apply_runner_event("linkedin_login_challenge_abort")
                except ImportError:
                    pass
                await browser.close()
                return {
                    "status": "error",
                    "message": "LinkedIn verification required. Complete login manually in a browser (https://linkedin.com), then retry. See docs/setup/job-apply-autofill-mcp.md for troubleshooting.",
                }
            await page.wait_for_timeout(2000)

            for job in jobs:
                await asyncio.sleep(random.uniform(max(5, rate_limit_seconds / 6), max(10, rate_limit_seconds / 4)))
                j = job if isinstance(job, dict) else {}
                url = j.get("url") or j.get("applyUrl") or ""
                if not url:
                    rr = RunResult(
                        status="skipped",
                        company=j.get("company", ""),
                        position=j.get("title", ""),
                        job_url="",
                        error="no_url",
                    )
                    run_results.append(rr)
                    results.append({"company": j.get("company", ""), "status": "skipped", "reason": "no_url"})
                    log_runner_result_to_tracker(j, rr, resume_path=config.resume_path or "")
                    continue
                result = await run_application(page, j, config, screenshot_dir=screenshot_dir)
                run_results.append(result)
                results.append(
                    {
                        "company": result.company,
                        "position": result.position,
                        "status": result.status,
                        "error": result.error or "",
                        "answerer_manual_review_required": answerer_review_pending(result.answerer_review),
                        "answerer_review_field_keys": list((result.answerer_review or {}).keys())[:12],
                    }
                )
                log_runner_result_to_tracker(j, result, resume_path=config.resume_path or "")
                if result.status == "applied":
                    applied += 1

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
