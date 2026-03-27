"""
Application Runner - Auto-apply engine. Fills forms using profile + application_answerer.
Supports:
- LinkedIn Easy Apply (primary)
- Greenhouse, Lever, Workday, and other external ATS (redirects from LinkedIn)
Resume renamed per job: {Name}_{Position}_at_{Company}_Resume.pdf
"""

import json
import os
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from playwright.async_api import Page
except ImportError:
    Page = None


def _browser_wait_multiplier() -> float:
    """
    Speed mode knobs for browser automation waits (Phase 5).

    Default multiplier is 1.0 to preserve existing behavior.
    When `CCP_FAST_BROWSER_PIPELINE=1`, use `CCP_BROWSER_WAIT_MULTIPLIER` (default 0.25).
    """
    fast = os.getenv("CCP_FAST_BROWSER_PIPELINE", "").strip().lower() in ("1", "true", "yes")
    if not fast:
        return 1.0
    try:
        return float(os.getenv("CCP_BROWSER_WAIT_MULTIPLIER", "0.25"))
    except (TypeError, ValueError):
        return 0.25


def _scaled_wait_ms(min_ms: int, max_ms: int) -> int:
    m = _browser_wait_multiplier()
    lo = max(0, int(min_ms * m))
    hi = max(1, int(max_ms * m))
    if lo >= hi:
        # Ensure a valid range; keep at least a small delay to reduce flakiness.
        lo = max(0, hi // 2)
    return random.randint(lo, hi)


@dataclass
class RunConfig:
    """Configuration for an application run."""
    resume_path: str = ""
    cover_letter_path: str = ""
    profile: dict = field(default_factory=dict)
    dry_run: bool = False
    # Phase 2 shadow: fill through pre-submit, never submit; statuses shadow_would_apply / shadow_would_not_apply
    shadow_mode: bool = False
    rate_limit_sec: float = 120.0
    confirm_before_submit: bool = True
    screenshots_dir: str = ""
    use_answerer: bool = True
    easy_apply_only: bool = True  # When True, only LinkedIn Easy Apply; reject external ATS
    # When True, LinkedIn live submit is skipped if any answerer-filled field has manual_review_required
    block_submit_on_answerer_review: bool = True


@dataclass
class RunResult:
    """Result of an application run."""
    status: str  # applied, skipped, failed, dry_run, shadow_would_apply, shadow_would_not_apply, ...
    company: str = ""
    position: str = ""
    job_url: str = ""
    applied_at: str = ""
    screenshot_paths: list = field(default_factory=list)
    qa_audit: dict = field(default_factory=dict)
    unmapped_fields: list = field(default_factory=list)
    error: str = ""
    # Filled fields sourced from application_answerer: label -> review metadata
    answerer_review: dict = field(default_factory=dict)


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
        # Explicit approved/job-specific resume overrides
        for key in ("approved_resume_path", "resume_path", "resume_pdf_path"):
            try:
                candidate = str(job.get(key) or "").strip()
            except Exception:
                candidate = ""
            if candidate and os.path.isfile(candidate):
                return candidate
        try:
            from services.resume_naming import ensure_resume_exists_for_job
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
    # Last resort: single primary from Master_Resumes only (not generated_resumes — those are job-specific)
    master_dir = proj / "Master_Resumes"
    if master_dir.exists():
        preferred = master_dir / "Master_Resume.pdf"
        if preferred.exists():
            return str(preferred)
        pdfs = sorted(master_dir.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
        if pdfs:
            return str(pdfs[0])
    return ""


def _get_value_and_meta_for_field(
    field_label: str, field_name: str, config: RunConfig, job: dict
) -> tuple[str, Optional[dict]]:
    """
    Map form field to value from profile or answerer.
    Returns (value, review_meta or None). review_meta is set for answerer-sourced fills.
    """
    label = (field_label or "").lower() + " " + (field_name or "").lower()
    profile = config.profile or {}

    for pattern, key, source in FIELD_MAPPINGS:
        if re.search(pattern, label, re.I):
            if source == "profile":
                val = profile.get(key, "")
                if key == "full_name" and val:
                    parts = str(val).strip().split()
                    if "first" in label or "given" in label:
                        return (parts[0] if parts else val), None
                    if "last" in label or "surname" in label:
                        return (parts[-1] if len(parts) > 1 else parts[0]), None
                return str(val or "").strip(), None
            if source == "answerer" and config.use_answerer:
                try:
                    from agents.application_answerer import answer_question_structured

                    job_ctx = {
                        "company": job.get("company", ""),
                        "title": job.get("title", ""),
                        "description": job.get("description", ""),
                    }
                    meta = answer_question_structured(key, profile=profile, job_context=job_ctx)
                    preview = (meta.get("answer") or "")[:100]
                    review = {
                        "manual_review_required": meta.get("manual_review_required", False),
                        "reason_codes": meta.get("reason_codes", []),
                        "classified_type": meta.get("classified_type", ""),
                        "value_preview": preview,
                        "question_used": key,
                    }
                    return meta.get("answer") or "", review
                except ImportError:
                    pass
    return "", None


def _get_value_for_field(field_label: str, field_name: str, config: RunConfig, job: dict) -> str:
    """Map form field to value from profile or answerer (string only)."""
    return _get_value_and_meta_for_field(field_label, field_name, config, job)[0]


def answerer_review_pending(answerer_review: Optional[dict]) -> bool:
    """True if any answerer-filled field requires manual confirmation."""
    if not answerer_review:
        return False
    return any(bool(v.get("manual_review_required")) for v in answerer_review.values())


async def fill_linkedin_easy_apply_modal(
    page: "Page",
    job: dict,
    config: RunConfig,
) -> tuple[dict, list, dict, dict[str, float]]:
    """
    Fill LinkedIn Easy Apply modal fields. Returns (qa_audit, unmapped_fields, answerer_review).
    Detects inputs, maps to profile/answerer, fills. Does not submit.
    """
    qa_audit: dict[str, str] = {}
    unmapped: list[str] = []
    answerer_review: dict = {}
    modal_total_start = time.perf_counter()
    value_resolution_seconds = 0.0
    field_fill_seconds = 0.0

    if not Page:
        return qa_audit, unmapped, answerer_review, {}

    # Speed mode: limit DOM scanning + skip some expensive label lookups.
    fast_browser = os.getenv("CCP_FAST_BROWSER_PIPELINE", "").strip().lower() in ("1", "true", "yes")
    max_fields = None
    if fast_browser:
        try:
            v = int(os.getenv("CCP_FAST_BROWSER_FIELDS_MAX", "25"))
            if v > 0:
                max_fields = v
        except (TypeError, ValueError):
            max_fields = 25

    # Prefer scoping queries to the Easy Apply modal dialog container.
    container_selectors = [
        "div[role='dialog']",
        "section[role='dialog']",
        "div.artdeco-modal__content",
    ]
    scoped_root: Optional[str] = None
    for cs in container_selectors:
        try:
            node = await page.query_selector(cs)
            if node and await node.is_visible():
                scoped_root = cs
                break
        except Exception:
            continue

    # Common input types in LinkedIn Easy Apply
    selectors = [
        "input[type='text']", "input[type='email']", "input[type='tel']",
        "textarea", "input:not([type])",
    ]
    filled_count = 0
    for sel in selectors:
        try:
            scoped_sel = f"{scoped_root} {sel}" if scoped_root else sel
            els = await page.query_selector_all(scoped_sel)
            for el in els:
                try:
                    if not await el.is_visible():
                        continue
                    name = await el.get_attribute("name") or ""
                    placeholder = await el.get_attribute("placeholder") or ""

                    if fast_browser:
                        # In speed mode, avoid the extra DOM lookup for label text.
                        label = ""
                        mapping_hint = (name + " " + placeholder).strip()
                    else:
                        label = ""
                        try:
                            el_id = await el.get_attribute("id") or ""
                            label_el = await page.query_selector(f"label[for='{el_id}']")
                            label = await label_el.inner_text() if label_el else ""
                        except Exception:
                            label = ""
                        mapping_hint = (label + " " + placeholder).strip()

                    v0 = time.perf_counter()
                    val, rev = _get_value_and_meta_for_field(mapping_hint, name, config, job)
                    value_resolution_seconds += time.perf_counter() - v0
                    if val:
                        f0 = time.perf_counter()
                        await el.fill(val)
                        field_fill_seconds += time.perf_counter() - f0
                        fk = label or name or placeholder or "field"
                        qa_audit[fk] = val[:100]
                        if rev:
                            answerer_review[fk] = rev
                        filled_count += 1
                        if max_fields is not None and filled_count >= max_fields:
                            modal_total_seconds = time.perf_counter() - modal_total_start
                            dom_scan_seconds = max(
                                0.0,
                                modal_total_seconds - value_resolution_seconds - field_fill_seconds,
                            )
                            timings = {
                                "linkedin_fill_dom_scan": dom_scan_seconds,
                                "linkedin_fill_value_resolution": value_resolution_seconds,
                                "linkedin_fill_field_fill": field_fill_seconds,
                            }
                            return qa_audit, unmapped, answerer_review, timings
                    else:
                        unmapped.append(label or name or placeholder or "unknown")
                except Exception:
                    continue
        except Exception:
            continue

    modal_total_seconds = time.perf_counter() - modal_total_start
    dom_scan_seconds = max(0.0, modal_total_seconds - value_resolution_seconds - field_fill_seconds)
    timings = {
        "linkedin_fill_dom_scan": dom_scan_seconds,
        "linkedin_fill_value_resolution": value_resolution_seconds,
        "linkedin_fill_field_fill": field_fill_seconds,
    }
    return qa_audit, unmapped, answerer_review, timings


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
    qa_audit: dict[str, str] = {}
    unmapped: list[str] = []
    answerer_review: dict = {}

    # Phase 7.3 performance telemetry: record where time goes in the Easy Apply fill path.
    t_total_start: Optional[float] = None
    linkedin_fill_goto_seconds: Optional[float] = None
    linkedin_fill_post_goto_wait_seconds: Optional[float] = None
    linkedin_fill_easy_apply_click_seconds: Optional[float] = None
    linkedin_fill_dom_scan_seconds: Optional[float] = None
    linkedin_fill_value_resolution_seconds: Optional[float] = None
    linkedin_fill_field_fill_seconds: Optional[float] = None
    linkedin_fill_resume_upload_seconds: Optional[float] = None
    linkedin_fill_screenshot_seconds: Optional[float] = None
    linkedin_live_submit_click_seconds: Optional[float] = None

    playwright_timeout_detected: bool = False

    try:
        t_total_start = time.perf_counter()

        t0 = time.perf_counter()
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        linkedin_fill_goto_seconds = time.perf_counter() - t0

        t0 = time.perf_counter()
        await page.wait_for_timeout(_scaled_wait_ms(2000, 4000))
        linkedin_fill_post_goto_wait_seconds = time.perf_counter() - t0

        # Click Easy Apply (same selector order as MCP confirm_easy_apply)
        from services.linkedin_easy_apply import LINKEDIN_EASY_APPLY_BUTTON_SELECTORS

        t_click_start = time.perf_counter()
        for sel in LINKEDIN_EASY_APPLY_BUTTON_SELECTORS:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click()
                    await page.wait_for_timeout(_scaled_wait_ms(3000, 3000))
                    break
            except Exception:
                continue
        linkedin_fill_easy_apply_click_seconds = time.perf_counter() - t_click_start

        # Fill text fields via profile + answerer
        qa_audit, unmapped, answerer_review, modal_timings = await fill_linkedin_easy_apply_modal(
            page,
            job,
            config,
        )
        linkedin_fill_dom_scan_seconds = (modal_timings or {}).get("linkedin_fill_dom_scan")
        linkedin_fill_value_resolution_seconds = (modal_timings or {}).get("linkedin_fill_value_resolution")
        linkedin_fill_field_fill_seconds = (modal_timings or {}).get("linkedin_fill_field_fill")

        # Resume upload + verification (LinkedIn Easy Apply)
        resume_path = _resolve_resume_path(config, job) or config.resume_path
        if not resume_path or not os.path.isfile(resume_path):
            qa_audit["resume_portal_error"] = "resume_file_missing"
            return RunResult(
                status="blocked_resume_verification",
                company=company,
                position=position,
                job_url=url,
                screenshot_paths=screenshot_paths,
                qa_audit=qa_audit,
                unmapped_fields=unmapped,
                answerer_review=answerer_review,
                error="resume_file_missing",
            )
        try:
            from services.resume_portal_adapter import LinkedInEasyApplyResumeAdapter
            from services.resume_upload_verifier import ensure_portal_resume

            t0 = time.perf_counter()
            portal_result = await ensure_portal_resume(
                page,
                resume_path,
                adapter=LinkedInEasyApplyResumeAdapter(),
                audit_context={
                    "job_id": str(job.get("job_id") or job.get("id") or ""),
                    "job_url": url,
                    "company": company,
                    "position": position,
                    "queue_state": str(job.get("queue_state") or job.get("job_state") or ""),
                },
            )
            linkedin_fill_resume_upload_seconds = time.perf_counter() - t0
            qa_audit["resume_portal_action"] = (portal_result.get("action") or "")[:80]
            qa_audit["resume_portal_status"] = (portal_result.get("status") or "")[:40]
            qa_audit["resume_expected"] = (portal_result.get("expected_filename") or "")[:120]
            qa_audit["resume_detected"] = (portal_result.get("detected_filename") or "")[:120]
            qa_audit["resume_verified"] = str(portal_result.get("verified", False))
            if portal_result.get("status") == "ok":
                qa_audit["resume_uploaded"] = os.path.basename(resume_path)
            else:
                qa_audit["resume_portal_error"] = (portal_result.get("error") or "")[:160]
                if screenshot_dir:
                    try:
                        screenshot_dir.mkdir(parents=True, exist_ok=True)
                        fname = f"resume_blocked_{company.replace(' ', '_')[:30]}_{datetime.now().strftime('%H%M%S')}.png"
                        fp = screenshot_dir / fname
                        await page.screenshot(path=str(fp))
                        screenshot_paths.append(str(fp))
                    except Exception:
                        pass
                return RunResult(
                    status="blocked_resume_verification",
                    company=company,
                    position=position,
                    job_url=url,
                    screenshot_paths=screenshot_paths,
                    qa_audit=qa_audit,
                    unmapped_fields=unmapped,
                    answerer_review=answerer_review,
                    error=portal_result.get("error") or "resume_verification_failed",
                )
        except Exception as exc:
            err = f"resume_verification_exception:{str(exc)[:120]}"
            qa_audit["resume_portal_error"] = err[:160]
            return RunResult(
                status="blocked_resume_verification",
                company=company,
                position=position,
                job_url=url,
                screenshot_paths=screenshot_paths,
                qa_audit=qa_audit,
                unmapped_fields=unmapped,
                answerer_review=answerer_review,
                error=err,
            )

        # Screenshot before submit
        if screenshot_dir:
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            fname = f"apply_{company.replace(' ', '_')[:30]}_{datetime.now().strftime('%H%M%S')}.png"
            fp = screenshot_dir / fname
            t0 = time.perf_counter()
            await page.screenshot(path=str(fp))
            linkedin_fill_screenshot_seconds = time.perf_counter() - t0
            screenshot_paths.append(str(fp))

        if config.dry_run and not config.shadow_mode:
            return RunResult(
                status="dry_run",
                company=company,
                position=position,
                job_url=url,
                screenshot_paths=screenshot_paths,
                qa_audit=qa_audit,
                unmapped_fields=unmapped,
                answerer_review=answerer_review,
            )

        if config.shadow_mode:
            if (
                config.block_submit_on_answerer_review
                and answerer_review_pending(answerer_review)
            ):
                return RunResult(
                    status="shadow_would_not_apply",
                    company=company,
                    position=position,
                    job_url=url,
                    screenshot_paths=screenshot_paths,
                    qa_audit=qa_audit,
                    unmapped_fields=unmapped,
                    answerer_review=answerer_review,
                    error=(
                        "answerer_manual_review_required: would not auto-submit "
                        "(shadow_mode)"
                    ),
                )
            return RunResult(
                status="shadow_would_apply",
                company=company,
                position=position,
                job_url=url,
                applied_at=datetime.now().isoformat(),
                screenshot_paths=screenshot_paths,
                qa_audit=qa_audit,
                unmapped_fields=unmapped,
                answerer_review=answerer_review,
                error="shadow_mode: filled through pre-submit; submit not clicked",
            )

        if (
            config.block_submit_on_answerer_review
            and answerer_review_pending(answerer_review)
        ):
            return RunResult(
                status="manual_assist_ready",
                company=company,
                position=position,
                job_url=url,
                screenshot_paths=screenshot_paths,
                qa_audit=qa_audit,
                unmapped_fields=unmapped,
                answerer_review=answerer_review,
                error="answerer_manual_review_required: confirm or edit answerer-filled fields before submit",
            )

        if config.confirm_before_submit:
            # Caller handles confirmation; we proceed to submit
            pass

        try:
            from services.autonomy_submit_gate import linkedin_live_submit_block_reason

            _gate = linkedin_live_submit_block_reason(job)
        except Exception:
            _gate = None
        if _gate:
            try:
                from services.apply_runner_metrics_redis import incr_apply_runner_event

                incr_apply_runner_event("linkedin_live_submit_blocked_autonomy")
            except Exception:
                pass
            return RunResult(
                status="skipped",
                company=company,
                position=position,
                job_url=url,
                screenshot_paths=screenshot_paths,
                qa_audit=qa_audit,
                unmapped_fields=unmapped,
                answerer_review=answerer_review,
                error=_gate,
            )

        try:
            from services.apply_runner_metrics_redis import incr_apply_runner_event

            incr_apply_runner_event("linkedin_live_submit_attempt")
        except Exception:
            pass

        # Submit
        for sel in ["button[aria-label*='Submit']", "button:has-text('Submit application')", "button:has-text('Submit')"]:
            try:
                submit = await page.query_selector(sel)
                if submit and await submit.is_visible():
                    t0 = time.perf_counter()
                    await submit.click()
                    await page.wait_for_timeout(_scaled_wait_ms(2000, 2000))
                    linkedin_live_submit_click_seconds = time.perf_counter() - t0
                    try:
                        from services.apply_runner_metrics_redis import incr_apply_runner_event

                        incr_apply_runner_event("linkedin_live_submit_success")
                    except Exception:
                        pass
                    return RunResult(
                        status="applied",
                        company=company,
                        position=position,
                        job_url=url,
                        applied_at=datetime.now().isoformat(),
                        screenshot_paths=screenshot_paths,
                        qa_audit=qa_audit,
                        unmapped_fields=unmapped,
                        answerer_review=answerer_review,
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
            answerer_review=answerer_review,
            error="Submit button not found",
        )

    except Exception as e:
        err = str(e)[:200]
        # Phase 7.4: Playwright timeout counter. (Timeout errors include "Timeout".)
        if "timeout" in err.lower():
            playwright_timeout_detected = True
        if screenshot_dir:
            try:
                screenshot_dir.mkdir(parents=True, exist_ok=True)
                fp = screenshot_dir / f"error_{company.replace(' ', '_')[:20]}.png"
                await page.screenshot(path=str(fp))
                screenshot_paths.append(str(fp))
            except Exception:
                pass
        return RunResult(
            status="failed",
            company=company,
            position=position,
            job_url=url,
            error=err,
            screenshot_paths=screenshot_paths,
            answerer_review=answerer_review,
        )

    finally:
        # Phase 7.3 performance telemetry: persist timings even when we return early.
        if t_total_start is not None:
            try:
                from services.apply_runner_metrics_redis import incr_apply_runner_duration

                incr_apply_runner_duration(
                    "linkedin_fill_total",
                    time.perf_counter() - t_total_start,
                )
                if linkedin_fill_goto_seconds is not None:
                    incr_apply_runner_duration("linkedin_fill_goto", linkedin_fill_goto_seconds)
                if linkedin_fill_post_goto_wait_seconds is not None:
                    incr_apply_runner_duration(
                        "linkedin_fill_post_goto_wait",
                        linkedin_fill_post_goto_wait_seconds,
                    )
                if linkedin_fill_easy_apply_click_seconds is not None:
                    incr_apply_runner_duration(
                        "linkedin_fill_easy_apply_click",
                        linkedin_fill_easy_apply_click_seconds,
                    )
                if linkedin_fill_dom_scan_seconds is not None:
                    incr_apply_runner_duration(
                        "linkedin_fill_dom_scan",
                        linkedin_fill_dom_scan_seconds,
                    )
                if linkedin_fill_value_resolution_seconds is not None:
                    incr_apply_runner_duration(
                        "linkedin_fill_value_resolution",
                        linkedin_fill_value_resolution_seconds,
                    )
                if linkedin_fill_field_fill_seconds is not None:
                    incr_apply_runner_duration(
                        "linkedin_fill_field_fill",
                        linkedin_fill_field_fill_seconds,
                    )
                if linkedin_fill_resume_upload_seconds is not None:
                    incr_apply_runner_duration(
                        "linkedin_fill_resume_upload",
                        linkedin_fill_resume_upload_seconds,
                    )
                if linkedin_fill_screenshot_seconds is not None:
                    incr_apply_runner_duration(
                        "linkedin_fill_screenshot",
                        linkedin_fill_screenshot_seconds,
                    )
                if linkedin_live_submit_click_seconds is not None:
                    incr_apply_runner_duration(
                        "linkedin_live_submit_click",
                        linkedin_live_submit_click_seconds,
                    )
                # Phase 7.4: unmapped fields proxy DOM drift / mapping issues.
                from services.apply_runner_metrics_redis import (
                    incr_apply_runner_event,
                    incr_apply_runner_unmapped_fields,
                )

                incr_apply_runner_unmapped_fields(len(unmapped))
                if playwright_timeout_detected:
                    incr_apply_runner_event("linkedin_fill_playwright_timeout")
            except Exception:
                pass


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
    qa_audit: dict[str, str] = {}
    unmapped: list[str] = []
    answerer_review: dict = {}

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(_scaled_wait_ms(2000, 4000))

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
                    await page.wait_for_timeout(_scaled_wait_ms(200, 600))
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
                    val, rev = _get_value_and_meta_for_field(label, name, config, job)
                    if val:
                        await el.fill(val)
                        fk = name or placeholder or "field"
                        qa_audit[fk] = val[:100]
                        if rev:
                            answerer_review[fk] = rev
            except Exception:
                continue

        # Resume upload
        resume_path = _resolve_resume_path(config, job) or config.resume_path
        if resume_path and os.path.isfile(resume_path):
            try:
                up = await page.query_selector("input[type='file']")
                if up and await up.is_visible():
                    await up.set_input_files(resume_path)
                    await page.wait_for_timeout(_scaled_wait_ms(1500, 1500))
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
                answerer_review=answerer_review,
            )

        # Never auto-submit external ATS; form filled for manual review
        return RunResult(
            status="manual_assist_ready",
            company=company,
            position=position,
            job_url=url,
            screenshot_paths=screenshot_paths,
            qa_audit=qa_audit,
            unmapped_fields=unmapped,
            answerer_review=answerer_review,
            error="External ATS: form filled. Review and submit manually.",
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
        return RunResult(
            status="failed",
            company=company,
            position=position,
            job_url=url,
            error=err,
            screenshot_paths=screenshot_paths,
            answerer_review=answerer_review,
        )


def _policy_blocked(job: dict) -> Optional[str]:
    """Check strict gate. Returns error string if blocked, None if allowed."""
    apply_mode = job.get("apply_mode", "")
    if apply_mode == "skip":
        return "policy_blocked: apply_mode=skip"
    if apply_mode and apply_mode != "auto_easy_apply":
        return f"policy_blocked: apply_mode={apply_mode}"
    fit = job.get("fit_decision", "")
    if fit and str(fit).lower() != "apply":
        return f"policy_blocked: fit_decision={fit}"
    ats = job.get("ats_score", job.get("final_ats_score"))
    if ats is not None and int(ats) < 85:
        return f"policy_blocked: ats_score={ats}<85"
    unsup = job.get("unsupported_requirements", [])
    if unsup:
        return "policy_blocked: unsupported_requirements"
    return None


async def run_application(
    page: "Page",
    job: dict,
    config: RunConfig,
    screenshot_dir: Optional[Path] = None,
) -> RunResult:
    """
    Run application for one job. Detects form type (LinkedIn vs external ATS) and routes.
    When easy_apply_only=True (default), only LinkedIn Easy Apply; external ATS is skipped.
    Strict gate: apply_mode=auto_easy_apply, fit_decision=apply, ats>=85, no unsupported.
    """
    url = job.get("url") or job.get("applyUrl") or ""
    company = job.get("company") or job.get("companyName", "")
    position = job.get("title") or job.get("jobTitle", "")
    form_type = detect_form_type(url)

    # Strict gate before LinkedIn auto-apply only
    if form_type == "linkedin":
        from services.truth_apply_gate import truth_apply_live_blocked_message

        _tg = truth_apply_live_blocked_message(
            config.profile,
            dry_run=bool(config.dry_run),
            shadow_mode=bool(config.shadow_mode),
        )
        if _tg:
            return RunResult(
                status="skipped",
                company=company,
                position=position,
                job_url=url,
                error=f"truth_apply_gate: {_tg}",
            )
        blocked = _policy_blocked(job)
        if blocked:
            return RunResult(status="skipped", company=company, position=position, job_url=url, error=blocked)
        return await run_linkedin_application(page, job, config, screenshot_dir)

    if config.easy_apply_only:
        return RunResult(
            status="skipped",
            company=company,
            position=position,
            job_url=url,
            error="easy_apply_only: external ATS (Greenhouse/Lever/Workday) not processed. Use manual_assist mode.",
        )
    # External ATS: fill for manual review, never auto-submit
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
            "answerer_review": getattr(r, "answerer_review", None) or {},
        }
        for r in results
    ]
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return str(fp)
