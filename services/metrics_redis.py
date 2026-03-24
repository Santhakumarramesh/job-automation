"""
Cross-process Celery / worker counters in Redis (Phase 3.6).

Enable with ``CELERY_METRICS_REDIS=1``. Uses key prefix ``ccp:metrics:`` on the
Redis instance from ``REDIS_METRICS_URL`` or falls back to ``REDIS_BROKER``.

Suitable for admin dashboards and simple alerting; not a full Prometheus replacement.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

_KEY_HASH = "ccp:metrics:celery"


def _enabled() -> bool:
    return os.getenv("CELERY_METRICS_REDIS", "").lower() in ("1", "true", "yes")


def _client():
    import redis

    url = (os.getenv("REDIS_METRICS_URL") or os.getenv("REDIS_BROKER") or "").strip()
    if not url:
        return None
    return redis.from_url(url, decode_responses=True)


def incr_celery_task(
    *,
    outcome: str,
    failure_class: str = "",
    duration_seconds: Optional[float] = None,
) -> None:
    """
    outcome: success | rejected | error
    failure_class: transient | permanent | "" (for errors)
    """
    if not _enabled():
        return
    try:
        r = _client()
        if r is None:
            return
        pipe = r.pipeline()
        pipe.hincrby(_KEY_HASH, f"tasks_{outcome}_total", 1)
        pipe.hincrby(_KEY_HASH, "tasks_total", 1)
        if failure_class:
            pipe.hincrby(_KEY_HASH, f"tasks_error_{failure_class}", 1)
        if duration_seconds is not None and duration_seconds >= 0:
            pipe.hincrbyfloat(_KEY_HASH, "task_duration_seconds_sum", float(duration_seconds))
            pipe.hincrby(_KEY_HASH, "task_duration_count", 1)
        pipe.hset(_KEY_HASH, "updated_at", str(int(time.time())))
        pipe.execute()
    except Exception:
        pass


def read_celery_metrics_hash() -> Dict[str, Any]:
    """
    Read ``ccp:metrics:celery`` from Redis for Prometheus bridge (Phase 4.3).

    Does **not** require ``CELERY_METRICS_REDIS`` on this process — only a Redis URL
    (``REDIS_METRICS_URL`` or ``REDIS_BROKER``).
    """
    try:
        r = _client()
        if r is None:
            return {"ok": False, "reason": "no_redis_url", "fields": {}}
        data = r.hgetall(_KEY_HASH) or {}
        return {"ok": True, "fields": data}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:500], "fields": {}}


def get_celery_metrics_summary() -> Dict[str, Any]:
    """Read aggregated hash; empty if disabled or Redis unavailable."""
    if not _enabled():
        return {"enabled": False, "reason": "CELERY_METRICS_REDIS not enabled"}
    try:
        r = _client()
        if r is None:
            return {"enabled": True, "error": "no Redis URL (REDIS_METRICS_URL / REDIS_BROKER)"}
        data = r.hgetall(_KEY_HASH)
        out: Dict[str, Any] = {"enabled": True, "hash": _KEY_HASH, "fields": data}
        # Parse numeric strings for convenience
        if data.get("task_duration_count"):
            try:
                cnt = int(data["task_duration_count"])
                s = float(data.get("task_duration_seconds_sum") or 0)
                out["avg_duration_seconds"] = round(s / cnt, 4) if cnt else None
            except (ValueError, TypeError):
                pass
        return out
    except Exception as e:
        return {"enabled": True, "error": str(e)[:500]}


def reset_celery_metrics() -> bool:
    """Admin / tests only — deletes the metrics hash."""
    if not _enabled():
        return False
    try:
        r = _client()
        if r is None:
            return False
        r.delete(_KEY_HASH)
        return True
    except Exception:
        return False
