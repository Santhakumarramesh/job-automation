"""Resolve ``ATSAdapter`` from job URL / job_source label."""

from __future__ import annotations

from typing import Any, Dict, Optional

from providers.ats.adapters import ADAPTER_BY_LABEL, UnknownAdapter
from providers.job_source import ATS_LINKEDIN_JOBS, ATS_UNKNOWN, detect_ats_provider


def get_ats_adapter_for_label(label: str):
    """Return adapter instance for a ``detect_ats_provider`` label."""
    cls = ADAPTER_BY_LABEL.get(label or ATS_UNKNOWN, UnknownAdapter)
    return cls()


def get_ats_adapter_for_job(job: Optional[dict] = None):
    """Infer label from ``job`` url / job_url / apply_url and return adapter."""
    j = job or {}
    listing = str(j.get("url") or j.get("job_url") or j.get("jobUrl") or "").strip()
    apply_u = str(j.get("apply_url") or j.get("applyUrl") or "").strip()
    primary = listing or apply_u
    label = detect_ats_provider(primary)
    return get_ats_adapter_for_label(label)


def describe_ats_platform(job: Optional[dict] = None, job_url: str = "", apply_url: str = "") -> Dict[str, Any]:
    """
    Serializable summary for MCP / API: provider, auto lane, manual tools.
    Pass either ``job`` dict or raw URLs.
    """
    if job_url or apply_url:
        job = {"url": job_url, "apply_url": apply_url}
    adapter = get_ats_adapter_for_job(job)
    listing = str((job or {}).get("url") or (job or {}).get("job_url") or "").strip()
    apply_u = str((job or {}).get("apply_url") or "").strip()
    apply_target = apply_u or listing

    listing_p = detect_ats_provider(listing) if listing else ATS_UNKNOWN
    target_p = detect_ats_provider(apply_target) if apply_target else ATS_UNKNOWN
    # Match policy: v1 auto only when both listing and resolved apply target stay on LinkedIn jobs.
    supports_auto = (
        adapter.supports_auto_apply_v1()
        and listing_p == ATS_LINKEDIN_JOBS
        and target_p == ATS_LINKEDIN_JOBS
    )

    return {
        "provider_id": adapter.provider_id,
        "listing_provider": listing_p,
        "apply_target_provider": target_p,
        "supports_auto_apply_v1": supports_auto,
        "v1_live_submit_policy": "linkedin_jobs_easy_apply_only",
        "manual_assist_capabilities": adapter.manual_assist_capabilities(),
        "analyze_form_preview": adapter.analyze_form(apply_target or listing),
    }
