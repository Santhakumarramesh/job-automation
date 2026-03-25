"""
Phase 4.3.3 — optional webhook when Redis Celery counters cross thresholds.

Intended for cron (e.g. every 10–15 minutes) with ``CELERY_METRICS_REDIS=1`` on a host
that can reach Redis (same vars as ``services.metrics_redis``).

Env:
  METRICS_ALERT_WEBHOOK_URL — required to POST (unless dry-run)
  METRICS_ALERT_WEBHOOK_TIMEOUT — seconds (default 15)
  METRICS_ALERT_ERROR_TOTAL_MIN — alert if ``tasks_error_total`` >= this (set to enable)
  METRICS_ALERT_ERROR_PERMANENT_MIN — alert if ``tasks_error_permanent`` >= this
  METRICS_ALERT_ERROR_TRANSIENT_MIN — alert if ``tasks_error_transient`` >= this
  METRICS_ALERT_REJECTED_TOTAL_MIN — alert if ``tasks_rejected_total`` >= this
  METRICS_ALERT_COOLDOWN_SECONDS — skip POST if last successful alert was within this window (default 3600); state file under ``data/.metrics_alert_last_sent``

At least one ``METRICS_ALERT_*_MIN`` must be set (integer >= 0) or the run no-ops.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_COOLDOWN_FILE = _PROJECT_ROOT / "data" / ".metrics_alert_last_sent"


def _int_field(fields: Dict[str, str], key: str) -> int:
    try:
        return int((fields.get(key) or "0").strip() or "0")
    except ValueError:
        return 0


def _optional_threshold(env_name: str) -> Optional[int]:
    raw = (os.getenv(env_name) or "").strip()
    if raw == "":
        return None
    try:
        v = int(raw)
        return max(0, v)
    except ValueError:
        return None


def _collect_reasons(fields: Dict[str, str]) -> List[str]:
    reasons: List[str] = []
    checks = [
        ("METRICS_ALERT_ERROR_TOTAL_MIN", "tasks_error_total", "tasks_error_total"),
        ("METRICS_ALERT_ERROR_PERMANENT_MIN", "tasks_error_permanent", "tasks_error_permanent"),
        ("METRICS_ALERT_ERROR_TRANSIENT_MIN", "tasks_error_transient", "tasks_error_transient"),
        ("METRICS_ALERT_REJECTED_TOTAL_MIN", "tasks_rejected_total", "tasks_rejected_total"),
    ]
    for env_k, field_k, label in checks:
        t = _optional_threshold(env_k)
        if t is None:
            continue
        cur = _int_field(fields, field_k)
        if cur >= t:
            reasons.append(f"{label}={cur} (>={t})")
    return reasons


def _cooldown_seconds() -> int:
    try:
        return max(0, int(os.getenv("METRICS_ALERT_COOLDOWN_SECONDS", "3600")))
    except ValueError:
        return 3600


def _last_sent_ts() -> float:
    try:
        if not _COOLDOWN_FILE.is_file():
            return 0.0
        return float(_COOLDOWN_FILE.read_text(encoding="utf-8").strip() or "0")
    except (ValueError, OSError):
        return 0.0


def _write_last_sent_ts(ts: float) -> None:
    try:
        _COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
        _COOLDOWN_FILE.write_text(str(ts), encoding="utf-8")
    except OSError:
        pass


def _within_cooldown() -> bool:
    cd = _cooldown_seconds()
    if cd <= 0:
        return False
    return (time.time() - _last_sent_ts()) < cd


def run_metrics_webhook_alert(*, dry_run: bool = False) -> Tuple[int, str]:
    """
    Returns (exit_code, message). 0 = ok / no alert needed; 1 = POST failed; 2 = misconfig.
    """
    from services.metrics_redis import get_celery_metrics_summary

    summary = get_celery_metrics_summary()
    if not summary.get("enabled"):
        return 0, "CELERY_METRICS_REDIS off or Redis unavailable — nothing to alert on."

    fields: Dict[str, str] = summary.get("fields") or {}
    if not any(
        _optional_threshold(x) is not None
        for x in (
            "METRICS_ALERT_ERROR_TOTAL_MIN",
            "METRICS_ALERT_ERROR_PERMANENT_MIN",
            "METRICS_ALERT_ERROR_TRANSIENT_MIN",
            "METRICS_ALERT_REJECTED_TOTAL_MIN",
        )
    ):
        return 0, "No METRICS_ALERT_*_MIN env vars set — nothing to evaluate."

    reasons = _collect_reasons(fields)
    if not reasons:
        return 0, "All metrics below configured thresholds."

    if _within_cooldown():
        return 0, f"Cooldown active ({_cooldown_seconds()}s) — skip POST."

    payload: Dict[str, Any] = {
        "source": "career-co-pilot-metrics",
        "reasons": reasons,
        "fields": dict(fields),
        "avg_duration_seconds": summary.get("avg_duration_seconds"),
    }

    if dry_run:
        return 0, f"dry-run:\n{json.dumps(payload, indent=2)}"

    url = (os.getenv("METRICS_ALERT_WEBHOOK_URL") or "").strip()
    if not url:
        return 2, "Set METRICS_ALERT_WEBHOOK_URL to POST."

    try:
        timeout = float(os.getenv("METRICS_ALERT_WEBHOOK_TIMEOUT", "15"))
    except ValueError:
        timeout = 15.0

    try:
        import requests

        r = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=max(5.0, timeout),
        )
    except Exception as e:
        return 1, f"POST failed: {e}"

    if r.status_code >= 400:
        return 1, f"POST HTTP {r.status_code}: {r.text[:500]}"

    _write_last_sent_ts(time.time())
    return 0, f"Posted alert ({r.status_code}): {', '.join(reasons)}"
