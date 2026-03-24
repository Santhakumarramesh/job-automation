"""
Normalize job URLs to an ATS / board label for policy, tracker, and future adapters.

v1: classification only (no per-platform DOM). Auto-submit remains LinkedIn **jobs** URLs only;
external apply targets (Greenhouse, Lever, etc.) force manual_assist.
"""

from __future__ import annotations

from urllib.parse import urlparse

# Stable labels for analytics / tracker / MCP (extend over time)
ATS_LINKEDIN_JOBS = "linkedin_jobs"
ATS_LINKEDIN_OTHER = "linkedin_other"
ATS_GREENHOUSE = "greenhouse"
ATS_LEVER = "lever"
ATS_WORKDAY = "workday"
ATS_DICE = "dice"
ATS_UNKNOWN = "unknown"
ATS_OTHER = "other"


def _host_path(url: str) -> tuple[str, str]:
    u = (url or "").strip()
    if not u:
        return "", ""
    if "://" not in u:
        u = "https://" + u
    try:
        p = urlparse(u)
        host = (p.netloc or "").lower()
        path = (p.path or "").lower()
        return host, path
    except Exception:
        return "", ""


def _is_linkedin_host(host: str) -> bool:
    if not host:
        return False
    return host == "linkedin.com" or host.endswith(".linkedin.com")


def _path_is_linkedin_jobs_view(path: str) -> bool:
    if not path:
        return False
    if "/jobs/" in path:
        return True
    p = path.rstrip("/")
    return p.endswith("/jobs")


def detect_ats_provider(url: str) -> str:
    """
    Best-effort board / ATS label from a job or apply URL.

    LinkedIn company pages, profiles, or generic linkedin.com paths are ``linkedin_other``,
    not ``linkedin_jobs`` (Easy Apply auto lane requires a /jobs/ URL).
    """
    host, path = _host_path(url)
    if not host:
        return ATS_UNKNOWN

    if _is_linkedin_host(host):
        return ATS_LINKEDIN_JOBS if _path_is_linkedin_jobs_view(path) else ATS_LINKEDIN_OTHER

    if "greenhouse.io" in host:
        return ATS_GREENHOUSE
    if "lever.co" in host:
        return ATS_LEVER
    if "myworkdayjobs.com" in host:
        return ATS_WORKDAY
    if host == "dice.com" or host.endswith(".dice.com"):
        return ATS_DICE

    return ATS_OTHER


def is_linkedin_jobs_listing_url(url: str) -> bool:
    """True only for LinkedIn job view / search URLs (v1 auto lane host check)."""
    return detect_ats_provider(url) == ATS_LINKEDIN_JOBS


def ats_metadata_for_job(job: dict) -> dict[str, str]:
    """Listing + resolved apply-target labels for exports and tracker enrichment."""
    j = job or {}
    listing = str(j.get("url") or j.get("job_url") or j.get("jobUrl") or "")
    apply_raw = str(j.get("apply_url") or j.get("applyUrl") or "").strip()
    apply_target = apply_raw or listing
    return {
        "ats_provider": detect_ats_provider(listing),
        "ats_provider_apply_target": detect_ats_provider(apply_target),
    }
