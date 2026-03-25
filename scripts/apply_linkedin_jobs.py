#!/usr/bin/env python3
"""
Apply to LinkedIn jobs using Playwright + Application Runner.
Uses jobs from JSON file (e.g. exported from Job Finder).
Fills form fields via candidate_profile + application_answerer.
Requires: pip install playwright && playwright install chromium
Env: LINKEDIN_EMAIL, LINKEDIN_PASSWORD, (optional) RESUME_PATH.
Live submit is skipped when any answerer-filled field has manual_review_required (default).
Override: pass RunConfig(block_submit_on_answerer_review=False) if you customize this script.
"""
import argparse
import asyncio
import json
import os
import random
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))


async def run_apply(
    jobs_path: str,
    resume_path: str = "",
    headless: bool = True,
    dry_run: bool = False,
    shadow_mode: bool = False,
    rate_limit: float = 120.0,
    *,
    allow_answerer_submit: bool = False,
):
    from playwright.async_api import async_playwright
    from agents.application_runner import RunConfig, run_application, save_run_results

    try:
        from services.profile_service import load_profile
        profile = load_profile()
    except ImportError:
        profile = {}

    with open(jobs_path) as f:
        data = json.load(f)
    jobs = data if isinstance(data, list) else data.get("jobs", [])
    if not jobs:
        print("No jobs in file.")
        return

    resume_path = resume_path or os.getenv("RESUME_PATH")
    if not resume_path:
        for p in [_ROOT / "Master_Resumes", _ROOT / "candidate_resumes", Path.home() / "Desktop" / "resume ai agent" / "Master_Resumes"]:
            if p.exists():
                for f in p.glob("*.pdf"):
                    resume_path = str(f)
                    break
            if resume_path:
                break
    if not resume_path:
        print("⚠️ No resume path. Set RESUME_PATH or add PDF to Master_Resumes/")

    config = RunConfig(
        resume_path=resume_path or "",
        profile=profile,
        dry_run=dry_run,
        shadow_mode=shadow_mode,
        rate_limit_sec=rate_limit,
        confirm_before_submit=not dry_run and not shadow_mode,
        screenshots_dir="application_runs/screenshots",
        use_answerer=True,
        block_submit_on_answerer_review=not allow_answerer_submit,
    )

    screenshot_dir = _ROOT / "application_runs" / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    email = os.getenv("LINKEDIN_EMAIL") or os.getenv("EMAIL")
    password = os.getenv("LINKEDIN_PASSWORD")
    if not email or not password:
        print("Set LINKEDIN_EMAIL and LINKEDIN_PASSWORD")
        return

    if shadow_mode:
        print("🌑 SHADOW MODE: Fill through pre-submit; never submit (shadow_would_apply / shadow_would_not_apply).")
    elif dry_run:
        print("🔬 DRY RUN: Will fill forms but NOT submit.")
    elif allow_answerer_submit:
        print("⚠️ allow_answerer_submit: will submit even if answerer fields need manual_review.")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print("Logging into LinkedIn...")
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

                incr_apply_runner_event("linkedin_login_checkpoint_pause")
            except ImportError:
                pass
            print("LinkedIn verification required. Complete in browser, then press Enter...")
            input()
        await page.wait_for_timeout(2000)

        results = []
        applied = 0
        for i, job in enumerate(jobs):
            title = job.get("title") or job.get("jobTitle", "Job")
            company = job.get("company") or job.get("companyName", "")
            print(f"\n[{i+1}/{len(jobs)}] {title} at {company}")
            await asyncio.sleep(random.uniform(max(5, rate_limit / 6), max(10, rate_limit / 4)))
            result = await run_application(page, job, config, screenshot_dir=screenshot_dir)
            results.append(result)
            print(f"  Status: {result.status}")
            if result.qa_audit:
                print(f"  Filled: {list(result.qa_audit.keys())[:5]}")
            if result.unmapped_fields:
                print(f"  Unmapped: {result.unmapped_fields[:3]}")
            ar = getattr(result, "answerer_review", None) or {}
            if ar:
                pending = [k for k, v in ar.items() if v.get("manual_review_required")]
                if pending:
                    print(f"  Answerer manual review: {pending[:5]}")
            try:
                from services.application_tracker import log_runner_result_to_tracker

                log_runner_result_to_tracker(
                    job,
                    result,
                    resume_path=config.resume_path or "",
                    user_id=(os.getenv("TRACKER_DEFAULT_USER_ID") or "cli-linkedin-apply").strip(),
                )
            except ImportError:
                pass
            if result.status == "applied":
                applied += 1

        await browser.close()

    save_path = save_run_results(results)
    print(f"\nDone. Applied to {applied}/{len(jobs)} jobs. Results: {save_path}")


def main():
    parser = argparse.ArgumentParser(description="Apply to LinkedIn jobs from JSON file")
    parser.add_argument("jobs_file", help="JSON file with jobs (list of {title, company, url})")
    parser.add_argument("--resume", default="", help="Resume PDF path")
    parser.add_argument("--no-headless", action="store_true", help="Show browser")
    parser.add_argument("--dry-run", action="store_true", help="Fill forms but do not submit")
    parser.add_argument(
        "--shadow",
        action="store_true",
        help="Phase 2 shadow: fill through pre-submit, never submit; tracker uses Shadow – Would Apply / Not Apply.",
    )
    parser.add_argument("--rate-limit", type=float, default=120.0, help="Min seconds between applications (default: 120)")
    parser.add_argument(
        "--allow-answerer-submit",
        action="store_true",
        help="Allow LinkedIn submit even when answerer-filled fields have manual_review_required (default: blocked).",
    )
    args = parser.parse_args()
    asyncio.run(run_apply(
        args.jobs_file, args.resume,
        headless=not args.no_headless,
        dry_run=args.dry_run,
        shadow_mode=args.shadow,
        rate_limit=args.rate_limit,
        allow_answerer_submit=args.allow_answerer_submit,
    ))


if __name__ == "__main__":
    main()
