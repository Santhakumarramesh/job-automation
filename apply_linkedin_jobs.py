#!/usr/bin/env python3
"""
Apply to LinkedIn jobs using Playwright.
Uses jobs from JSON file (e.g. exported from Job Finder).
Requires: pip install playwright && playwright install chromium
Env: LINKEDIN_EMAIL, LINKEDIN_PASSWORD, (optional) RESUME_PATH
"""
import argparse
import asyncio
import json
import os
import random
import sys
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).resolve().parent))


async def apply_to_linkedin(page, job: dict, resume_path: str) -> str:
    """LinkedIn Easy Apply flow. Returns Applied | Skipped | Error."""
    url = job.get("url") or job.get("applyUrl") or ""
    if not url or "linkedin.com" not in url:
        return "Skipped"
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(random.randint(2000, 4000))

        for sel in [
            "button[aria-label*='Easy Apply']",
            "button:has-text('Easy Apply')",
            "button:has-text('Apply now')",
            "[data-control-name='apply_from_job_card']",
            "button.jobs-apply-button",
        ]:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click()
                    await page.wait_for_timeout(3000)
                    if resume_path and os.path.isfile(resume_path):
                        up = await page.query_selector("input[type='file']")
                        if up:
                            await up.set_input_files(resume_path)
                            await page.wait_for_timeout(1500)
                    submit = await page.query_selector("button[aria-label*='Submit'], button:has-text('Submit application')")
                    if submit and await submit.is_visible():
                        await submit.click()
                        await page.wait_for_timeout(2000)
                    return "Applied"
            except Exception:
                continue
        return "Skipped"
    except Exception as e:
        return f"Error: {str(e)[:60]}"


async def run_apply(jobs_path: str, resume_path: str = "", headless: bool = True):
    from playwright.async_api import async_playwright

    with open(jobs_path) as f:
        data = json.load(f)
    jobs = data if isinstance(data, list) else data.get("jobs", [])
    if not jobs:
        print("No jobs in file.")
        return

    resume_path = resume_path or os.getenv("RESUME_PATH")
    if not resume_path:
        for p in [Path(__file__).parent / "Master_Resumes", Path(__file__).parent / "candidate_resumes", Path.home() / "Desktop" / "resume ai agent" / "Master_Resumes"]:
            if p.exists():
                for f in p.glob("*.pdf"):
                    resume_path = str(f)
                    break
            if resume_path:
                break
    if not resume_path:
        print("⚠️ No resume path. Set RESUME_PATH or add PDF to Master_Resumes/")

    email = os.getenv("LINKEDIN_EMAIL") or os.getenv("EMAIL")
    password = os.getenv("LINKEDIN_PASSWORD")
    if not email or not password:
        print("Set LINKEDIN_EMAIL and LINKEDIN_PASSWORD")
        return

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
            print("LinkedIn verification required. Complete in browser, then press Enter...")
            input()
        await page.wait_for_timeout(2000)

        applied = 0
        for i, job in enumerate(jobs):
            title = job.get("title") or job.get("jobTitle", "Job")
            company = job.get("company") or job.get("companyName", "")
            print(f"\n[{i+1}/{len(jobs)}] {title} at {company}")
            await asyncio.sleep(random.uniform(8, 15))
            status = await apply_to_linkedin(page, job, resume_path or "")
            print(f"  Status: {status}")
            if status == "Applied":
                applied += 1

        await browser.close()
    print(f"\nDone. Applied to {applied}/{len(jobs)} jobs.")


def main():
    parser = argparse.ArgumentParser(description="Apply to LinkedIn jobs from JSON file")
    parser.add_argument("jobs_file", help="JSON file with jobs (list of {title, company, url})")
    parser.add_argument("--resume", default="", help="Resume PDF path")
    parser.add_argument("--no-headless", action="store_true", help="Show browser")
    args = parser.parse_args()
    asyncio.run(run_apply(args.jobs_file, args.resume, headless=not args.no_headless))


if __name__ == "__main__":
    main()
