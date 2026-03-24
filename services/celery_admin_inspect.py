"""
Phase 4.2.3 — Celery ``control.inspect`` snapshot for operators (stuck / active tasks).

Best-effort: returns **None** for worker keys when no workers answer (common if workers
are down). Requires the API process to reach the same broker as workers
(``REDIS_BROKER`` / Celery app config).

Env:
  CELERY_INSPECT_TIMEOUT — default ``2.0`` (seconds) passed to ``inspect(timeout=…)``.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Tuple


def _timeout_sec() -> float:
    try:
        return max(0.5, min(30.0, float(os.getenv("CELERY_INSPECT_TIMEOUT", "2.0"))))
    except ValueError:
        return 2.0


def celery_inspect_snapshot(*, timeout_sec: float | None = None) -> Dict[str, Any]:
    """
    Run a bounded ``inspect()`` round-trip. Safe to call from FastAPI (sync route);
    Celery applies the timeout on the broker RPC.
    """
    t = timeout_sec if timeout_sec is not None else _timeout_sec()
    try:
        from app.tasks import celery
    except Exception as e:
        return {"ok": False, "error": f"celery_app_import: {e}"}

    try:
        insp = celery.control.inspect(timeout=t)
        if insp is None:
            return {
                "ok": False,
                "error": "inspect() returned None — check REDIS_BROKER and that workers use the same app name.",
                "timeout_sec": t,
            }
    except Exception as e:
        return {"ok": False, "error": str(e)[:500], "timeout_sec": t}

    checks: List[Tuple[str, Callable[[], Any]]] = [
        ("ping", insp.ping),
        ("active", insp.active),
        ("reserved", insp.reserved),
        ("scheduled", insp.scheduled),
        ("stats", insp.stats),
    ]
    workers: Dict[str, Any] = {}
    for name, fn in checks:
        try:
            workers[name] = fn()
        except Exception as ex:
            workers[name] = {"_error": str(ex)[:300]}

    return {"ok": True, "timeout_sec": t, "workers": workers}
