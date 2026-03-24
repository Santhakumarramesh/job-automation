"""
Optional read-only DOM probe for application pages (inputs/selects/textareas).

Gated by ``ATS_ALLOW_LIVE_FORM_PROBE=1`` at the API/MCP layer. Does not submit forms.
Many boards (LinkedIn logged-in, bot detection) may return partial or empty results.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def live_form_probe_enabled() -> bool:
    return os.getenv("ATS_ALLOW_LIVE_FORM_PROBE", "").lower() in ("1", "true", "yes")


def live_form_probe_disabled_response() -> Dict[str, Any]:
    """Shared payload for API 403 detail text and MCP when the live probe env gate is off."""
    return {
        "status": "disabled",
        "message": "Set ATS_ALLOW_LIVE_FORM_PROBE=1 to enable live DOM probing.",
    }


def _allowed_http_url(url: str) -> bool:
    try:
        p = urlparse((url or "").strip())
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False


def _truncate(s: str | None, n: int = 200) -> str:
    if not s:
        return ""
    s = str(s).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def probe_apply_page_fields(url: str, *, max_fields: int = 40, timeout_ms: int = 25_000) -> Dict[str, Any]:
    """
    Load ``url`` in headless Chromium and list up to ``max_fields`` form controls.
    Read-only; never clicks Apply or submits.
    """
    target = (url or "").strip()
    if not target:
        return {"status": "error", "message": "url is empty", "fields": [], "field_count": 0}
    if not _allowed_http_url(target):
        return {"status": "error", "message": "Only http(s) URLs with a host are allowed.", "fields": [], "field_count": 0}

    host = _truncate(urlparse(target).netloc, 120)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {
            "status": "error",
            "message": "playwright is not installed (pip install playwright && playwright install chromium).",
            "fields": [],
            "field_count": 0,
        }

    fields: List[Dict[str, Any]] = []
    page_title = ""
    final_url = target
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    )
                )
                page = context.new_page()
                page.set_default_timeout(timeout_ms)
                page.goto(target, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(1200)
                page_title = _truncate(page.title(), 300)
                final_url = _truncate(page.url, 2000)
                handles = page.query_selector_all("input, select, textarea")
                for el in handles[: max(1, min(max_fields, 120))]:
                    try:
                        tag = (el.evaluate("e => e.tagName.toLowerCase()") or "").strip()
                        if tag == "input":
                            typ = (el.get_attribute("type") or "text").lower()
                            if typ in ("hidden", "submit", "button", "image"):
                                continue
                        name = _truncate(el.get_attribute("name"), 120)
                        eid = _truncate(el.get_attribute("id"), 120)
                        ph = _truncate(el.get_attribute("placeholder"), 160)
                        aria = _truncate(el.get_attribute("aria-label"), 160)
                        req = el.get_attribute("required") is not None
                        fields.append(
                            {
                                "tag": tag,
                                "type": (el.get_attribute("type") or "").lower() if tag == "input" else "",
                                "name": name,
                                "id": eid,
                                "placeholder": ph,
                                "aria_label": aria,
                                "required": req,
                            }
                        )
                    except Exception:
                        continue
                context.close()
            finally:
                browser.close()
    except Exception as e:
        logger.info(
            "live_form_probe host=%s status=error field_count=%s",
            host,
            len(fields),
        )
        return {
            "status": "error",
            "message": _truncate(str(e), 500),
            "fields": fields,
            "field_count": len(fields),
            "page_title": page_title,
            "final_url": final_url,
        }

    logger.info(
        "live_form_probe host=%s status=ok field_count=%s",
        host,
        len(fields),
    )
    return {
        "status": "ok",
        "message": "",
        "fields": fields,
        "field_count": len(fields),
        "page_title": page_title,
        "final_url": final_url,
    }
