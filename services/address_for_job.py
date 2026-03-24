"""
Select a truthful mailing address for a job posting from the candidate profile.

Uses ``mailing_address`` as default and optional ``alternate_mailing_addresses`` entries
with ``regions_served`` string lists matched against the job location / title / snippet.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.job_location_match import haystack_matches_region, job_is_remoteish, job_location_haystack
from services.profile_service import format_mailing_address_dict


def get_address_for_job(job: Optional[dict], profile: Optional[dict]) -> Dict[str, Any]:
    """
    Return structured address pick for forms and audit.

    Keys:
      - ``mailing_address``: dict (street/city/state/postal/country) — may be empty if unset
      - ``address_label``: ``\"default\"`` or alternate's ``label``
      - ``used_alternate``: bool
      - ``selection_reason``: short human-readable explanation
      - ``mailing_address_oneline``: formatted for copy/paste
    """
    job = job or {}
    profile = profile or {}
    default_ma = profile.get("mailing_address")
    if not isinstance(default_ma, dict):
        default_ma = {}

    hay = job_location_haystack(job)
    if job_is_remoteish(job):
        oneline = format_mailing_address_dict(default_ma)
        return {
            "mailing_address": default_ma,
            "address_label": "default",
            "used_alternate": False,
            "selection_reason": "Remote or hybrid role — using default mailing_address.",
            "mailing_address_oneline": oneline,
        }

    alternates = profile.get("alternate_mailing_addresses")
    if isinstance(alternates, list):
        for alt in alternates:
            if not isinstance(alt, dict):
                continue
            label = str(alt.get("label") or "").strip() or "alternate"
            ma = alt.get("mailing_address")
            if not isinstance(ma, dict):
                continue
            regions = alt.get("regions_served")
            if not isinstance(regions, list):
                regions = []
            region_strs: List[str] = [str(x).strip() for x in regions if str(x).strip()]
            for r in region_strs:
                if haystack_matches_region(hay, r):
                    oneline = format_mailing_address_dict(ma)
                    return {
                        "mailing_address": ma,
                        "address_label": label,
                        "used_alternate": True,
                        "selection_reason": (
                            f"Job text matches regions_served {r!r} for alternate label {label!r}."
                        ),
                        "mailing_address_oneline": oneline,
                    }

    oneline = format_mailing_address_dict(default_ma)
    return {
        "mailing_address": default_ma,
        "address_label": "default",
        "used_alternate": False,
        "selection_reason": "No alternate_mailing_addresses region matched job location; using default mailing_address.",
        "mailing_address_oneline": oneline,
    }


def address_for_job_payload(
    job_location: str = "",
    job_title: str = "",
    job_description: str = "",
    work_type: str = "",
) -> dict:
    """
    MCP ``get_address_for_job`` + REST parity: load profile and return selection + ``status``.
    """
    try:
        from services.profile_service import load_profile

        profile = load_profile()
        job = {
            "location": job_location,
            "title": job_title,
            "description": job_description,
            "work_type": work_type,
        }
        sel = get_address_for_job(job, profile)
        return {
            "status": "ok",
            "mailing_address": sel["mailing_address"],
            "mailing_address_oneline": sel["mailing_address_oneline"],
            "address_label": sel["address_label"],
            "used_alternate": sel["used_alternate"],
            "selection_reason": sel["selection_reason"],
        }
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}
