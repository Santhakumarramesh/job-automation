"""Shared ATS form analysis payload for MCP and REST (v1 = static hints + platform metadata)."""

from __future__ import annotations

from typing import Any, Dict


def run_analyze_form(*, job_url: str = "", apply_url: str = "") -> Dict[str, Any]:
    from providers.ats.registry import describe_ats_platform, get_ats_adapter_for_job

    job = {"url": job_url, "apply_url": apply_url}
    adapter = get_ats_adapter_for_job(job)
    target = (apply_url or job_url or "").strip()
    preview = adapter.analyze_form(target)
    meta = describe_ats_platform(job_url=job_url, apply_url=apply_url)
    meta.pop("analyze_form_preview", None)
    return {
        "status": "ok",
        "provider_id": adapter.provider_id,
        "platform": meta,
        "form_analysis": preview,
    }
