"""
Phase 3 — narrow autonomy: operator gates before LinkedIn live submit.

Default behavior is **unchanged** (submit allowed) unless env vars are set.

Env
---

- ``AUTONOMY_LINKEDIN_LIVE_SUBMIT_DISABLED`` — if ``1`` / ``true`` / ``yes``, block **all**
  live LinkedIn submits (dry_run and shadow_mode unaffected).

- ``AUTONOMY_LINKEDIN_PILOT_SUBMIT_ONLY`` — if ``1`` / ``true`` / ``yes``, allow live submit
  only when **any** of:
  - the job dict has ``pilot_submit_allowed: true`` (or legacy ``pilot_submit: true``), or
  - ``AUTONOMY_LINKEDIN_PILOT_USER_IDS`` is non-empty and ``user_id`` or
    ``authenticated_user_id`` on the job matches a comma-separated entry, or
  - ``AUTONOMY_LINKEDIN_PILOT_WORKSPACE_IDS`` is non-empty and ``workspace_id`` or
    ``organization_id`` on the job matches a comma-separated entry.

  If both allowlist env vars are empty or unset, only the per-job pilot flags apply (same as v0).

- ``AUTONOMY_LINKEDIN_ROLLBACK_WHEN_FAILURE_RATE_GTE`` — optional float in ``(0, 1]``.
  When set, and Redis has at least ``AUTONOMY_LINKEDIN_ROLLBACK_MIN_ATTEMPTS`` live-submit
  attempts (``linkedin_live_submit_attempt_total``), block new live submits if
  ``(attempt - success) / attempt`` is **≥** this threshold. Requires a Redis URL
  (``REDIS_METRICS_URL`` / ``REDIS_BROKER``). Evaluated after the kill switch and before
  pilot-only rules.

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


def _csv_id_set(env_name: str) -> set[str]:
    raw = os.getenv(env_name, "") or ""
    return {x.strip() for x in raw.split(",") if x.strip()}


def _rollback_failure_rate_block_reason() -> Optional[str]:
    raw = os.getenv("AUTONOMY_LINKEDIN_ROLLBACK_WHEN_FAILURE_RATE_GTE", "").strip()
    if not raw:
        return None
    try:
        threshold = float(raw)
    except ValueError:
        return None
    if not (0.0 < threshold <= 1.0):
        return None
    try:
        min_attempts = int(os.getenv("AUTONOMY_LINKEDIN_ROLLBACK_MIN_ATTEMPTS", "10") or "10")
    except ValueError:
        min_attempts = 10
    if min_attempts < 1:
        min_attempts = 1
    try:
        from services.apply_runner_metrics_redis import read_linkedin_live_submit_totals
    except Exception:
        return None
    totals = read_linkedin_live_submit_totals()
    if totals is None:
        return None
    attempt, success = totals
    if attempt < min_attempts:
        return None
    failure_rate = (attempt - success) / float(attempt)
    if failure_rate + 1e-12 >= threshold:
        return (
            "autonomy: telemetry rollback — live submit failure rate "
            f"{failure_rate:.3f} >= {threshold:g} over {attempt} attempts "
            "(AUTONOMY_LINKEDIN_ROLLBACK_WHEN_FAILURE_RATE_GTE); adjust env or Redis counters"
        )
    return None


def _job_in_pilot_allowlists(job: Dict[str, Any]) -> bool:
    """True if user_id or workspace_id matches non-empty env allowlists."""
    users = _csv_id_set("AUTONOMY_LINKEDIN_PILOT_USER_IDS")
    workspaces = _csv_id_set("AUTONOMY_LINKEDIN_PILOT_WORKSPACE_IDS")
    if not users and not workspaces:
        return False
    uid = str(job.get("user_id") or job.get("authenticated_user_id") or "").strip()
    wid = str(job.get("workspace_id") or job.get("organization_id") or "").strip()
    if uid and uid in users:
        return True
    if wid and wid in workspaces:
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
    _rb = _rollback_failure_rate_block_reason()
    if _rb:
        return _rb
    if _truthy_env("AUTONOMY_LINKEDIN_PILOT_SUBMIT_ONLY"):
        j = dict(job or {})
        if _job_pilot_flag(j):
            return None
        if _job_in_pilot_allowlists(j):
            return None
        users = _csv_id_set("AUTONOMY_LINKEDIN_PILOT_USER_IDS")
        workspaces = _csv_id_set("AUTONOMY_LINKEDIN_PILOT_WORKSPACE_IDS")
        if users or workspaces:
            return (
                "autonomy: pilot_submit_only — job not in pilot allowlist "
                "(pilot_submit_allowed / pilot_submit, or user_id/workspace_id matching "
                "AUTONOMY_LINKEDIN_PILOT_USER_IDS / AUTONOMY_LINKEDIN_PILOT_WORKSPACE_IDS)"
            )
        return (
            "autonomy: pilot_submit_only — set pilot_submit_allowed: true on this job "
            "(AUTONOMY_LINKEDIN_PILOT_SUBMIT_ONLY=1)"
        )
    return None
