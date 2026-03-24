"""
Optional job location gate vs profile ``application_locations``.

Enable with ``POLICY_ENFORCE_JOB_LOCATION=1``. When the profile lists target locations,
jobs whose location text does not match any listed place (and are not allowed-remote)
are skipped or downgraded per ``check_job_location_policy``.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

REASON_SKIP_JOB_LOCATION = "skip_job_location_outside_application_locations"
REASON_MANUAL_JOB_LOCATION_UNKNOWN = "manual_assist_job_location_unknown"


def _enforce() -> bool:
    return os.getenv("POLICY_ENFORCE_JOB_LOCATION", "").lower() in ("1", "true", "yes")


def _job_haystack(job: dict) -> str:
    j = job or {}
    parts = [
        str(j.get("location") or j.get("locationName") or j.get("job_location") or ""),
        str(j.get("title") or j.get("position") or ""),
        str(j.get("work_type") or ""),
        str(j.get("description") or j.get("job_description") or "")[:600],
    ]
    return " ".join(parts).lower()


def _is_remoteish(hay: str, job: dict) -> bool:
    wt = str(job.get("work_type") or "").lower()
    if wt in ("remote", "hybrid"):
        return True
    return "remote" in hay or "work from home" in hay


def _tokens_from_profile_locs(locs: List[Any]) -> List[str]:
    out: List[str] = []
    for raw in locs:
        if not isinstance(raw, dict):
            continue
        for key in ("label", "city", "state_region", "country"):
            v = str(raw.get(key) or "").strip()
            if len(v) >= 2:
                out.append(v.lower())
    return out


def _token_matches_haystack(hay: str, token: str) -> bool:
    t = token.strip().lower()
    if len(t) < 2:
        return False
    if len(t) == 2:
        return re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", hay) is not None
    return t in hay


def job_location_haystack(job: dict) -> str:
    """Normalized lowercase text blob for job location / work mode (shared with address routing)."""
    return _job_haystack(job)


def job_is_remoteish(job: dict) -> bool:
    """True if job appears remote or hybrid from work_type or description/title."""
    return _is_remoteish(_job_haystack(job), job or {})


def haystack_matches_region(hay: str, region: str) -> bool:
    """True if ``region`` (city, state, country, metro label) plausibly appears in ``hay``."""
    t = str(region or "").strip().lower()
    if len(t) < 2:
        return False
    return _token_matches_haystack(hay, t)


def check_job_location_policy(job: dict, profile: Optional[dict]) -> Tuple[str, str]:
    """
    Returns (\"ok\", \"\") to continue the rest of ``decide_apply_mode_with_reason``,
    or (\"skip\"|\"manual_assist\", reason) to return immediately.
    """
    if not _enforce():
        return "ok", ""
    profile = profile or {}
    locs = profile.get("application_locations")
    if not isinstance(locs, list) or not locs:
        return "ok", ""

    hay = _job_haystack(job)
    if not hay.strip():
        return "manual_assist", REASON_MANUAL_JOB_LOCATION_UNKNOWN

    remote_ok_any = any(isinstance(x, dict) and x.get("remote_ok") is True for x in locs)

    if _is_remoteish(hay, job):
        if remote_ok_any:
            return "ok", ""
        return "skip", REASON_SKIP_JOB_LOCATION

    tokens = _tokens_from_profile_locs(locs)
    if not tokens:
        return "ok", ""

    for tok in tokens:
        if _token_matches_haystack(hay, tok):
            return "ok", ""

    return "skip", REASON_SKIP_JOB_LOCATION
