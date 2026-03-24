"""
LinkedIn Easy Apply DOM probes (MCP / runner). Selector list is centralized for tests and tuning.
"""

from __future__ import annotations

from typing import List, Tuple

# Ordered: more specific / stable first, then broader fallbacks.
LINKEDIN_EASY_APPLY_BUTTON_SELECTORS: List[str] = [
    "button[aria-label*='Easy Apply']",
    "button[aria-label*='easy apply']",
    "button[data-control-name='job_apply_button']",
    "button.jobs-apply-button",
    ".jobs-apply-button--top-card button",
    "div.jobs-s-apply button",
    "button:has-text('Easy Apply')",
    "button:has-text('Apply now')",
    "a[data-tracking-control-name='public_jobs_apply-link']",
    "[data-control-name='apply_from_job_card']",
    "button[aria-label*='Apply']",
    "div[data-job-id] button.jobs-apply-button",
]


async def find_visible_easy_apply_button(page) -> Tuple[bool, str | None, List[str]]:
    """
    Return (found, matched_selector_or_none, selectors_tried_in_order).
    ``page`` is a Playwright async Page.
    """
    tried: List[str] = []
    for sel in LINKEDIN_EASY_APPLY_BUTTON_SELECTORS:
        tried.append(sel)
        try:
            btn = await page.query_selector(sel)
            if btn is not None and await btn.is_visible():
                return True, sel, tried
        except Exception:
            continue
    return False, None, tried
