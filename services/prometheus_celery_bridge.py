"""
Mirror Redis Celery aggregate counters into Prometheus Gauges (Phase 4.3).

Workers increment hash ``ccp:metrics:celery`` when ``CELERY_METRICS_REDIS=1``.
The API process refreshes **Gauge** values on each ``GET /metrics`` scrape so
Prometheus can alert without Pushgateway.

Enable when ``PROMETHEUS_METRICS=1`` and either:

- ``PROMETHEUS_CELERY_REDIS=1`` (read Redis even if this process does not set
  ``CELERY_METRICS_REDIS``), or
- ``CELERY_METRICS_REDIS=1`` (same as admin metrics summary).

Disable bridge only: ``PROMETHEUS_CELERY_REDIS=0``.

Gauges mirror monotonic Redis counters; use ``increase()`` / ``rate()`` in PromQL.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

# (redis_hash_field, prometheus_name, help)
_CELERY_GAUGE_SPECS: Tuple[Tuple[str, str, str], ...] = (
    ("tasks_total", "ccp_celery_tasks_total", "Terminal Celery tasks (all outcomes, from Redis)"),
    ("tasks_success_total", "ccp_celery_tasks_success_total", "Celery tasks finished success"),
    ("tasks_rejected_total", "ccp_celery_tasks_rejected_total", "Celery tasks rejected (e.g. guard)"),
    ("tasks_error_total", "ccp_celery_tasks_error_total", "Celery tasks finished error"),
    ("tasks_error_transient", "ccp_celery_tasks_error_transient_total", "Errors classified transient"),
    ("tasks_error_permanent", "ccp_celery_tasks_error_permanent_total", "Errors classified permanent"),
    ("task_duration_seconds_sum", "ccp_celery_task_duration_seconds_sum", "Sum of task wall times (seconds)"),
    ("task_duration_count", "ccp_celery_task_duration_count", "Count of tasks with duration recorded"),
)

_gauges: Dict[str, Any] = {}
_registered: bool = False


def celery_redis_bridge_enabled() -> bool:
    p = (os.getenv("PROMETHEUS_CELERY_REDIS") or "").strip().lower()
    if p in ("0", "false", "no"):
        return False
    if p in ("1", "true", "yes"):
        return True
    return os.getenv("CELERY_METRICS_REDIS", "").strip().lower() in ("1", "true", "yes")


def register_celery_redis_gauges(registry: Any) -> bool:
    """Register Gauges on ``registry``. Idempotent. Returns False if bridge disabled."""
    global _registered, _gauges
    if _registered:
        return bool(_gauges)
    if not celery_redis_bridge_enabled():
        return False
    from prometheus_client import Gauge

    _gauges = {}
    for field, name, doc in _CELERY_GAUGE_SPECS:
        _gauges[field] = Gauge(name, doc, registry=registry)
    _registered = True
    return True


def refresh_celery_redis_gauges() -> None:
    """Update registered Gauges from Redis; no-op if not registered."""
    if not _gauges:
        return
    from services.metrics_redis import read_celery_metrics_hash

    snap = read_celery_metrics_hash()
    fields: Dict[str, str] = snap.get("fields") or {}
    if not snap.get("ok"):
        for g in _gauges.values():
            try:
                g.set(0.0)
            except Exception:
                pass
        return

    for field, gauge in _gauges.items():
        raw = (fields.get(field) or "0").strip() or "0"
        try:
            gauge.set(float(raw))
        except (ValueError, TypeError):
            try:
                gauge.set(0.0)
            except Exception:
                pass


def registered_gauge_fields() -> List[str]:
    """Test helper: Redis hash fields that have a matching Gauge."""
    return [s[0] for s in _CELERY_GAUGE_SPECS]


def reset_celery_bridge_state_for_tests() -> None:
    """Clear module registration state (unit tests only)."""
    global _registered, _gauges
    _registered = False
    _gauges = {}
