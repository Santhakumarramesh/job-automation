"""
Phase 3 — narrow autonomy: operator gates before LinkedIn live submit.

Default behavior is **unchanged** (submit allowed) unless env vars are set.

Env
---

- ``AUTONOMY_LINKEDIN_LIVE_SUBMIT_DISABLED`` — if ``1`` / ``true`` / ``yes``, block **all**
  live LinkedIn submits (dry_run and shadow_mode unaffected).

- ``AUTONOMY_LINKEDIN_PILOT_SUBMIT_ONLY`` — if ``1`` / ``true`` / ``yes``, allow live submit
  only when the job dict has ``pilot_submit_allowed: true`` (or legacy ``pilot_submit: true``).

Use together: e.g. pilot-only in staging, kill switch in incident response.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def _job_pilot_flag(job: Dict[str, Any]) -> bool:
    j = job or {}
    if bool(j.get("pilot_submit_allowed")):
        return True
    if bool(j.get("pilot_submit")):
        return True
    return False


def linkedin_live_submit_block_reason(job: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """
    If live LinkedIn submit must be blocked, return a stable error string for RunResult;
    else ``None``.
    """
    if _truthy_env("AUTONOMY_LINKEDIN_LIVE_SUBMIT_DISABLED"):
        return (
            "autonomy: live LinkedIn submit disabled "
            "(AUTONOMY_LINKEDIN_LIVE_SUBMIT_DISABLED=1)"
        )
    if _truthy_env("AUTONOMY_LINKEDIN_PILOT_SUBMIT_ONLY"):
        j = job or {}
        if not _job_pilot_flag(j):
            return (
                "autonomy: pilot_submit_only — set pilot_submit_allowed: true on this job "
                "(AUTONOMY_LINKEDIN_PILOT_SUBMIT_ONLY=1)"
            )
    return None
