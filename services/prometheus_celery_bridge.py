"""
Mirror Redis aggregate metrics into Prometheus Gauges.

Phase 4.3: Celery counters
  - Workers increment hash ``ccp:metrics:celery`` when ``CELERY_METRICS_REDIS=1``.

Phase 7.2: Apply-runner timing samples
  - Browser automation timings are written into hash ``ccp:metrics:apply_runner``
    via ``services.apply_runner_metrics_redis.incr_apply_runner_duration``.

The API process refreshes **Gauge** values on each ``GET /metrics`` scrape so
Prometheus can alert without Pushgateway.
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

_APPLY_RUNNER_DURATION_STAGES: Tuple[str, ...] = (
    "linkedin_fill_total",
    "linkedin_fill_goto",
    "linkedin_fill_post_goto_wait",
    "linkedin_fill_easy_apply_click",
    "linkedin_fill_dom_scan",
    "linkedin_fill_value_resolution",
    "linkedin_fill_field_fill",
    "linkedin_fill_resume_upload",
    "linkedin_fill_screenshot",
    "linkedin_live_submit_click",
)


def _apply_runner_duration_gauge_specs() -> Tuple[Tuple[str, str, str], ...]:
    """
    Build gauge specs from known Redis stage keys.

    Redis keys:
      - ``{stage}_seconds_sum``
      - ``{stage}_seconds_count``
    Prometheus keys:
      - ``ccp_apply_runner_{stage}_seconds_sum``
      - ``ccp_apply_runner_{stage}_seconds_count``
    """

    out: list[Tuple[str, str, str]] = []
    for stage in _APPLY_RUNNER_DURATION_STAGES:
        redis_sum_field = f"{stage}_seconds_sum"
        redis_count_field = f"{stage}_seconds_count"
        out.append(
            (
                redis_sum_field,
                f"ccp_apply_runner_{stage}_seconds_sum",
                f"Apply-runner stage {stage}: sum of wall time seconds (from Redis)",
            )
        )
        out.append(
            (
                redis_count_field,
                f"ccp_apply_runner_{stage}_seconds_count",
                f"Apply-runner stage {stage}: count of timing samples (from Redis)",
            )
        )
    return tuple(out)


_APPLY_RUNNER_GAUGE_SPECS: Tuple[Tuple[str, str, str], ...] = _apply_runner_duration_gauge_specs()

_gauges: Dict[str, Any] = {}
_registered: bool = False


def celery_redis_bridge_enabled() -> bool:
    p = (os.getenv("PROMETHEUS_CELERY_REDIS") or "").strip().lower()
    if p in ("0", "false", "no"):
        return False
    if p in ("1", "true", "yes"):
        return True
    return os.getenv("CELERY_METRICS_REDIS", "").strip().lower() in ("1", "true", "yes")


def apply_runner_redis_bridge_enabled() -> bool:
    """
    Whether to expose apply-runner timing Redis fields to Prometheus.

    Default: same enablement as Celery bridge.
    """

    p = (os.getenv("PROMETHEUS_APPLY_RUNNER_REDIS") or "").strip().lower()
    if p in ("0", "false", "no"):
        return False
    if p in ("1", "true", "yes"):
        return True
    return celery_redis_bridge_enabled()


def register_celery_redis_gauges(registry: Any) -> bool:
    """
    Register Gauges on ``registry``. Idempotent.

    Returns False only if the bridge is disabled entirely (Celery enablement false).
    """
    global _registered, _gauges
    if _registered:
        return bool(_gauges)
    if not celery_redis_bridge_enabled():
        return False
    from prometheus_client import Gauge

    _gauges = {}
    for field, name, doc in _CELERY_GAUGE_SPECS:
        _gauges[field] = Gauge(name, doc, registry=registry)
    if apply_runner_redis_bridge_enabled():
        for field, name, doc in _APPLY_RUNNER_GAUGE_SPECS:
            _gauges[field] = Gauge(name, doc, registry=registry)
    _registered = True
    return True


def refresh_celery_redis_gauges() -> None:
    """
    Update registered Gauges from Redis; no-op if not registered.

    Celery fields come from ``ccp:metrics:celery``.
    Apply-runner timing fields come from ``ccp:metrics:apply_runner``.
    """
    if not _gauges:
        return
    from services.metrics_redis import read_celery_metrics_hash

    snap = read_celery_metrics_hash()
    fields: Dict[str, str] = snap.get("fields") or {}

    if not snap.get("ok"):
        # If Celery metrics are down, still try apply-runner timing metrics if enabled.
        # Celery dashboards will read zeros; timing dashboards will work when Redis is reachable.
        fields = {}

    if apply_runner_redis_bridge_enabled():
        try:
            from services.apply_runner_metrics_redis import read_apply_runner_metrics_summary

            ar = read_apply_runner_metrics_summary()
            if isinstance(ar, dict):
                af = ar.get("fields") or {}
                if isinstance(af, dict):
                    # Merge; whichever redis field exists will be used by the gauge key.
                    fields = {**fields, **af}
        except Exception:
            pass

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
    return [s[0] for s in (_CELERY_GAUGE_SPECS + _APPLY_RUNNER_GAUGE_SPECS)]


def reset_celery_bridge_state_for_tests() -> None:
    """Clear module registration state (unit tests only)."""
    global _registered, _gauges
    _registered = False
    _gauges = {}
