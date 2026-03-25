"""
Optional Redis counters for LinkedIn apply / browser automation (Phase 4.5.1).

Enable with ``APPLY_RUNNER_METRICS_REDIS=1``. Uses the same Redis URL as Celery metrics
(``REDIS_METRICS_URL`` or ``REDIS_BROKER``). Hash: ``ccp:metrics:apply_runner``.

Events (fixed set — do not pass arbitrary strings from user input):
  - ``linkedin_login_checkpoint_pause`` — interactive script paused for human verification
  - ``linkedin_login_challenge_abort`` — headless flow stopped at LinkedIn challenge URL
  - ``linkedin_live_submit_attempt`` — reached live submit (after autonomy gate)
  - ``linkedin_live_submit_success`` — submit click path returned applied
  - ``linkedin_live_submit_blocked_autonomy`` — blocked by ``autonomy_submit_gate`` (kill switch / pilot-only / telemetry rollback)

``read_linkedin_live_submit_totals()`` returns ``(attempt_total, success_total)`` from the hash for telemetry rollback (no ``APPLY_RUNNER_METRICS_REDIS`` gate on read).

``read_linkedin_nonsubmit_pattern_totals()`` returns ``(nonsubmit_total, denom_total)`` for pattern rollback:
``nonsubmit = checkpoint_pause + challenge_abort``, ``denom = nonsubmit + live_submit_attempt_total`` (live-submit attempts proxy for flows that reached the autonomy gate).
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional, Tuple

_KEY_HASH = "ccp:metrics:apply_runner"

_ALLOWED_EVENTS = frozenset(
    {
        "linkedin_login_checkpoint_pause",
        "linkedin_login_challenge_abort",
        "linkedin_live_submit_attempt",
        "linkedin_live_submit_success",
        "linkedin_live_submit_blocked_autonomy",
    }
)


def apply_runner_metrics_enabled() -> bool:
    return os.getenv("APPLY_RUNNER_METRICS_REDIS", "").lower() in ("1", "true", "yes")


def _client():
    try:
        import redis
    except ImportError:
        return None
    url = (os.getenv("REDIS_METRICS_URL") or os.getenv("REDIS_BROKER") or "").strip()
    if not url:
        return None
    return redis.from_url(url, decode_responses=True)


def incr_apply_runner_event(event: str) -> None:
    """Increment counter ``{event}_total`` in the apply-runner metrics hash."""
    if not apply_runner_metrics_enabled():
        return
    key = (event or "").strip()
    if key not in _ALLOWED_EVENTS:
        return
    try:
        r = _client()
        if r is None:
            return
        field = f"{key}_total"
        pipe = r.pipeline()
        pipe.hincrby(_KEY_HASH, field, 1)
        pipe.hset(_KEY_HASH, "updated_at", str(int(time.time())))
        pipe.execute()
    except Exception:
        pass


_ATTEMPT_FIELD = "linkedin_live_submit_attempt_total"
_SUCCESS_FIELD = "linkedin_live_submit_success_total"
_CHECKPOINT_FIELD = "linkedin_login_checkpoint_pause_total"
_CHALLENGE_ABORT_FIELD = "linkedin_login_challenge_abort_total"


def _int_field(h: Dict[str, str], key: str) -> int:
    try:
        return int(float(h.get(key) or "0"))
    except (TypeError, ValueError):
        return 0


def read_linkedin_live_submit_totals() -> Optional[Tuple[int, int]]:
    """
    Return ``(attempt_total, success_total)`` from Redis, or ``None`` if Redis is unavailable.

    Used by ``autonomy_submit_gate`` telemetry rollback. Does **not** require
    ``APPLY_RUNNER_METRICS_REDIS=1`` — reads whatever counters exist in the hash.
    """
    try:
        r = _client()
        if r is None:
            return None
        h = r.hgetall(_KEY_HASH) or {}
        a_raw = h.get(_ATTEMPT_FIELD) or "0"
        s_raw = h.get(_SUCCESS_FIELD) or "0"
        attempt = int(float(a_raw))
        success = int(float(s_raw))
        if success > attempt:
            success = attempt
        return (attempt, success)
    except Exception:
        return None


def read_linkedin_nonsubmit_pattern_totals() -> Optional[Tuple[int, int]]:
    """
    Return ``(nonsubmit_total, denom_total)`` for pattern-level rollback, or ``None`` if Redis is unavailable.

    ``nonsubmit`` counts login checkpoint pauses and challenge aborts (incremented from browser automation).
    ``denom = nonsubmit + linkedin_live_submit_attempt_total`` so friction is measured against flows
    that either hit those events or progressed to a live submit attempt.
    """
    try:
        r = _client()
        if r is None:
            return None
        h = r.hgetall(_KEY_HASH) or {}
        cp = max(0, _int_field(h, _CHECKPOINT_FIELD))
        ab = max(0, _int_field(h, _CHALLENGE_ABORT_FIELD))
        att = max(0, _int_field(h, _ATTEMPT_FIELD))
        nonsubmit = cp + ab
        denom = nonsubmit + att
        return (nonsubmit, denom)
    except Exception:
        return None


def read_apply_runner_metrics_summary() -> Dict[str, Any]:
    """Read hash for admin JSON / dashboards (no env gate on read)."""
    try:
        r = _client()
        if r is None:
            return {
                "enabled": apply_runner_metrics_enabled(),
                "hash": _KEY_HASH,
                "fields": {},
                "error": "no Redis URL (REDIS_METRICS_URL / REDIS_BROKER)",
            }
        data = r.hgetall(_KEY_HASH) or {}
        return {
            "enabled": apply_runner_metrics_enabled(),
            "hash": _KEY_HASH,
            "fields": data,
        }
    except Exception as e:
        return {
            "enabled": apply_runner_metrics_enabled(),
            "hash": _KEY_HASH,
            "fields": {},
            "error": str(e)[:500],
        }
