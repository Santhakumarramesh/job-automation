"""
Application Runner - Auto-apply engine. Fills forms using profile + application_answerer.
Supports:
- LinkedIn Easy Apply (primary)
- Greenhouse, Lever, Workday, and other external ATS (redirects from LinkedIn)
Resume renamed per job: {Name}_{Position}_at_{Company}_Resume.pdf
"""

import asyncio
import json
import os
import random
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    from playwright.async_api import Page
except ImportError:
    Page = None  # type: ignore


@dataclass
class RunConfig:
    """Configuration for an application run."""
    resume_path: str = ""
    cover_letter_path: str = ""
    profile: dict = field(default_factory=dict)
    dry_run: bool = False
    rate_limit_sec: float = 120.0
    confirm_before_submit: bool = True
    screenshots_dir: str = ""
    use_answerer: bool = True


@dataclass
class RunResult:
    """Result of an application run."""
    status: str  # applied, skipped, failed, dry_run
    company: str = ""
    position: str = ""
    job_url: str = ""
    applied_at: str = ""
    screenshot_paths: list = field(default_factory=list)
    qa_audit: dict = field(default_factory=dict)
    unmapped_fields: list = field(default_factory=list)
    error: str = ""


# Field name patterns -> profile key or answerer question
FIELD_MAPPINGS = [
    (r"email|e-?mail", "email", "profile"),
    (r"phone|mobile|telephone", "phone", "profile"),
    (r"first\s*name|given\s*name", "full_name", "profile"),  # use first part
    (r"last\s*name|surname|family", "full_name", "profile"),   # use last part
    (r"sponsor|work\s*auth|visa|authorization", "Do you require sponsorship?", "answerer"),
    (r"relocat|willing\s*to\s*move", "relocation_preference", "profile"),
    (r"salary|compensation|pay", "What is your expected salary?", "answerer"),
    (r"years?\s*(of\s*)?(exp|experience)", "How many years of experience do you have?", "answerer"),
    (r"why\s*this\s*role|why\s*position", "Why do you want this role?", "answerer"),
    (r"why\s*company|why\s*us", "Why do you want to work at this company?", "answerer"),
    (r"when\s*start|availability", "availability", "profile"),
    (r"notice\s*period", "notice_period", "profile"),
    (r"linkedin|linked\s*in", "linkedin_url", "profile"),
    (r"github", "github_url", "profile"),
    (r"portfolio|website", "portfolio_url", "profile"),
]


def _resolve_resume_path(config: RunConfig, job: Optional[dict] = None) -> str:
    """Resolve resume path. Prefer job-specific path if exists."""
    proj = Path(__file__).resolve().parent.parent
    if job:
        try:
            from services.resume_naming import resume_path_for_job, ensure_resume_exists_for_job
            profile = config.profile or {}
            name = profile.get("full_name", "") or os.getenv("CANDIDATE_NAME", "")
            path = ensure_resume_exists_for_job(
                job,
                resume_content_path=config.resume_path or os.getenv("RESUME_PATH"),
                candidate_name=name,
            )
            if path:
                return path
        except ImportError:
            pass
    if config.resume_path and os.path.isfile(config.resume_path):
        return config.resume_path
    path = os.getenv("RESUME_PATH")
    if path and os.path.isfile(path):
        return path
    for base in [proj / "Master_Resumes", proj / "generated_resumes", proj / "candidate_resumes"]:
        if base.exists():
            for f in base.rglob("*.pdf"):
                return str(f)
    return ""


def _get_value_for_field(field_label: str, field_name: str, config: RunConfig, job: dict) -> str:
    """Map form field to value from profile or answerer."""
    label = (field_label or "").lower() + " " + (field_name or "").lower()
    profile = config.profile or {}

    for pattern, key, source in FIELD_MAPPINGS:
        if re.search(pattern, label, re.I):
            if source == "profile":
                val = profile.get(key, "")
                if key == "full_name" and val:
                    parts = str(val).strip().split()
                    if "first" in label or "given" in label:
                        return parts[0] if parts else val
                    if "last" in label or "surname" in label:
                        return parts[-1] if len(parts) > 1 else parts[0]
                return str(val or "").strip()
            if source == "answerer" and config.use_answerer:
                try:
                    from agents.application_answerer import answer_question
                    job_ctx = {"company": job.get("company", ""), "title": job.get("title", ""), "description": job.get("description", "")}
                    return answer_question(key, profile=profile, job_context=job_ctx)
                except ImportError:
                    pass
    return ""


async def fill_linkedin_easy_apply_modal(
    page: "Page",
    job: dict,
    config: RunConfig,
) -> tuple[dict, list]:
    """
    Fill LinkedIn Easy Apply modal fields. Returns (qa_audit, unmapped_fields).
    Detects inputs, maps to profile/answerer, fills. Does not submit.
    """
    qa_audit = {}
    unmapped = []

    if not Page:
        return qa_audit, unmapped

    # Common input types in LinkedIn Easy Apply
    selectors = [
        "input[type='text']", "input[type='email']", "input[type='tel']",
        "textarea", "input:not([type])",
    ]
    for sel in selectors:
        try:
            els = await page.query_selector_all(sel)
            for el in els:
                try:
                    if not await el.is_visible():
                        continue
                    name = await el.get_attribute("name") or ""
                    label_el = await page.query_selector(f"label[for='{await el.get_attribute('id') or ''}']")
                    label = await label_el.inner_text() if label_el else ""
                    placeholder = await el.get_attribute("placeholder") or ""
                    val = _get_value_for_field(label + " " + placeholder, name, config, job)
                    if val:
                        await el.fill(val)
                        qa_audit[label or name or placeholder or "field"] = val[:100]
                    else:
                        unmapped.append(label or name or placeholder or "unknown")
                except Exception:
                    continue
        except Exception:
            continue

    return qa_audit, unmapped


async def run_linkedin_application(
    page: "Page",
    job: dict,
    config: RunConfig,
    screenshot_dir: Optional[Path] = None,
) -> RunResult:
    """
    Run LinkedIn Easy Apply for one job. Fills form, optionally submits.
    Returns RunResult with status, qa_audit, screenshots.
    """
    url = job.get("url") or job.get("applyUrl") or ""
    company = job.get("company") or job.get("companyName", "")
    position = job.get("title") or job.get("jobTitle", "")

    if not url or "linkedin.com" not in url:
        return RunResult(status="skipped", company=company, position=position, job_url=url)

    if not Page:
        return RunResult(status="failed", company=company, position=position, job_url=url, error="Playwright not installed")

    screenshot_paths = []
    qa_audit = {}
    unmapped = []

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(random.randint(2000, 4000))

        # Click Easy Apply
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
                    break
            except Exception:
                continue

        # Fill text fields via profile + answerer
        qa_audit, unmapped = await fill_linkedin_easy_apply_modal(page, job, config)

        # Resume upload (use job-specific path when available)
        resume_path = _resolve_resume_path(config, job) or config.resume_path
        if resume_path and os.path.isfile(resume_path):
            try:
                up = await page.query_selector("input[type='file']")
                if up and await up.is_visible():
                    await up.set_input_files(resume_path)
                    await page.wait_for_timeout(1500)
                    qa_audit["resume_uploaded"] = os.path.basename(resume_path)
            except Exception:
                unmapped.append("resume_upload")

        # Screenshot before submit
        if screenshot_dir:
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            fname = f"apply_{company.replace(' ', '_')[:30]}_{datetime.now().strftime('%H%M%S')}.png"
            fp = screenshot_dir / fname
            await page.screenshot(path=str(fp))
            screenshot_paths.append(str(fp))

        if config.dry_run:
            return RunResult(
                status="dry_run",
                company=company,
                position=position,
                job_url=url,
                screenshot_paths=screenshot_paths,
                qa_audit=qa_audit,
                unmapped_fields=unmapped,
            )

        if config.confirm_before_submit:
            # Caller handles confirmation; we proceed to submit
            pass

        # Submit
        for sel in ["button[aria-label*='Submit']", "button:has-text('Submit application')", "button:has-text('Submit')"]:
            try:
                submit = await page.query_selector(sel)
                if submit and await submit.is_visible():
                    await submit.click()
                    await page.wait_for_timeout(2000)
                    return RunResult(
                        status="applied",
                        company=company,
                        position=position,
                        job_url=url,
                        applied_at=datetime.now().isoformat(),
                        screenshot_paths=screenshot_paths,
                        qa_audit=qa_audit,
                        unmapped_fields=unmapped,
                    )
            except Exception:
                continue

        return RunResult(
            status="skipped",
            company=company,
            position=position,
            job_url=url,
            screenshot_paths=screenshot_paths,
            qa_audit=qa_audit,
            unmapped_fields=unmapped,
            error="Submit button not found",
        )

    except Exception as e:
        err = str(e)[:200]
        if screenshot_dir:
            try:
                screenshot_dir.mkdir(parents=True, exist_ok=True)
                fp = screenshot_dir / f"error_{company.replace(' ', '_')[:20]}.png"
                await page.screenshot(path=str(fp))
                screenshot_paths.append(str(fp))
            except Exception:
                pass
        return RunResult(status="failed", company=company, position=position, job_url=url, error=err, screenshot_paths=screenshot_paths)


# --- External ATS: Greenhouse, Lever, Workday ---
EXTERNAL_ATS_PATTERNS = [
    ("greenhouse", ["greenhouse.io", "boards.greenhouse.io", "jobs.greenhouse.io"]),
    ("lever", ["lever.co", "jobs.lever.co"]),
    ("workday", ["workday.com", "myworkdayjobs.com"]),
]


def detect_form_type(url: str) -> str:
    """Detect form type from URL. Returns: linkedin, greenhouse, lever, workday, generic."""
    if not url:
        return "generic"
    lower = url.lower()
    if "linkedin.com" in lower:
        return "linkedin"
    for ats_type, patterns in EXTERNAL_ATS_PATTERNS:
        if any(p in lower for p in patterns):
            return ats_type
    return "generic"


async def fill_external_ats_form(
    page: "Page",
    job: dict,
    config: RunConfig,
    form_type: str = "generic",
    screenshot_dir: Optional[Path] = None,
) -> RunResult:
    """
    Fill Greenhouse, Lever, Workday, or generic external ATS form.
    Uses profile + answerer for field values. Returns RunResult.
    """
    url = job.get("url") or job.get("applyUrl") or ""
    company = job.get("company") or job.get("companyName", "")
    position = job.get("title") or job.get("jobTitle", "")

    if not Page:
        return RunResult(status="failed", company=company, position=position, job_url=url, error="Playwright not installed")

    screenshot_paths = []
    qa_audit = {}
    unmapped = []

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(random.randint(2000, 4000))

        # Common selectors for external ATS (Greenhouse/Lever/Workday patterns)
        profile = config.profile or {}
        name = str(profile.get("full_name", "") or os.getenv("CANDIDATE_NAME", "")).strip()
        parts = name.split()
        first_name = parts[0] if parts else ""
        last_name = parts[-1] if len(parts) > 1 else first_name
        email = profile.get("email", "") or os.getenv("LINKEDIN_EMAIL", os.getenv("EMAIL", ""))
        phone = profile.get("phone", "") or os.getenv("PHONE", "")

        for sel, val in [
            ("input[name*='email'], input[id*='email'], input[type='email']", email),
            ("input[name*='first'], input[name*='firstName'], input[id*='first']", first_name),
            ("input[name*='last'], input[name*='lastName'], input[id*='last']", last_name),
            ("input[name*='phone'], input[id*='phone'], input[type='tel']", phone),
        ]:
            if not val:
                continue
            try:
                inp = await page.query_selector(sel)
                if inp and await inp.is_visible():
                    await inp.fill(str(val))
                    qa_audit[sel[:30]] = str(val)[:50]
                    await page.wait_for_timeout(random.randint(200, 600))
            except Exception:
                continue

        # Fill textareas and other inputs via profile/answerer
        for sel in ["textarea", "input[type='text']:not([name*='email'])"]:
            try:
                els = await page.query_selector_all(sel)
                for el in els:
                    if not await el.is_visible():
                        continue
                    name = await el.get_attribute("name") or await el.get_attribute("id") or ""
                    placeholder = await el.get_attribute("placeholder") or ""
                    label = (name + " " + placeholder).lower()
                    val = _get_value_for_field(label, name, config, job)
                    if val:
                        await el.fill(val)
                        qa_audit[name or placeholder or "field"] = val[:100]
            except Exception:
                continue

        # Resume upload
        resume_path = _resolve_resume_path(config, job) or config.resume_path
        if resume_path and os.path.isfile(resume_path):
            try:
                up = await page.query_selector("input[type='file']")
                if up and await up.is_visible():
                    await up.set_input_files(resume_path)
                    await page.wait_for_timeout(1500)
                    qa_audit["resume_uploaded"] = os.path.basename(resume_path)
            except Exception:
                unmapped.append("resume_upload")

        if screenshot_dir:
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            fname = f"apply_{company.replace(' ', '_')[:30]}_{datetime.now().strftime('%H%M%S')}.png"
            fp = screenshot_dir / fname
            await page.screenshot(path=str(fp))
            screenshot_paths.append(str(fp))

        if config.dry_run:
            return RunResult(
                status="dry_run",
                company=company,
                position=position,
                job_url=url,
                screenshot_paths=screenshot_paths,
                qa_audit=qa_audit,
                unmapped_fields=unmapped,
            )

        # Submit
        for sel in [
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Submit')",
            "button:has-text('Submit Application')",
            "button:has-text('Apply')",
            "[data-action='submit']",
        ]:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click()
                    await page.wait_for_timeout(3000)
                    return RunResult(
                        status="applied",
                        company=company,
                        position=position,
                        job_url=url,
                        applied_at=datetime.now().isoformat(),
                        screenshot_paths=screenshot_paths,
                        qa_audit=qa_audit,
                        unmapped_fields=unmapped,
                    )
            except Exception:
                continue

        return RunResult(
            status="skipped",
            company=company,
            position=position,
            job_url=url,
            screenshot_paths=screenshot_paths,
            qa_audit=qa_audit,
            unmapped_fields=unmapped,
            error="Submit button not found",
        )

    except Exception as e:
        err = str(e)[:200]
        if screenshot_dir:
            try:
                screenshot_dir.mkdir(parents=True, exist_ok=True)
                fp = screenshot_dir / f"error_{company.replace(' ', '_')[:20]}.png"
                await page.screenshot(path=str(fp))
                screenshot_paths.append(str(fp))
            except Exception:
                pass
        return RunResult(status="failed", company=company, position=position, job_url=url, error=err, screenshot_paths=screenshot_paths)


async def run_application(
    page: "Page",
    job: dict,
    config: RunConfig,
    screenshot_dir: Optional[Path] = None,
) -> RunResult:
    """
    Run application for one job. Detects form type (LinkedIn vs external ATS) and routes.
    Uses job-specific resume naming when tailored resume exists.
    """
    url = job.get("url") or job.get("applyUrl") or ""
    form_type = detect_form_type(url)
    if form_type == "linkedin":
        return await run_linkedin_application(page, job, config, screenshot_dir)
    return await fill_external_ats_form(page, job, config, form_type, screenshot_dir)


def save_run_results(results: list[RunResult], output_dir: str = "application_runs") -> str:
    """Save run results and Q&A audit to JSON. Returns path."""
    from pathlib import Path
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    fname = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    fp = out / fname
    data = [
        {
            "status": r.status,
            "company": r.company,
            "position": r.position,
            "job_url": r.job_url,
            "applied_at": r.applied_at,
            "screenshot_paths": r.screenshot_paths,
            "qa_audit": r.qa_audit,
            "unmapped_fields": r.unmapped_fields,
            "error": r.error,
        }
        for r in results
    ]
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return str(fp)
