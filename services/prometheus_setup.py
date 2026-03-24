"""
Optional Prometheus scrape endpoint + HTTP request counter (Phase 3.6).

Set ``PROMETHEUS_METRICS=1`` and install ``pip install .[metrics]``.

- ``GET /metrics`` — Prometheus text format (process + ``ccp_http_requests_total``).
- Paths are grouped to limit cardinality (e.g. ``/api/applications`` not per-id URLs).

Protect ``/metrics`` at your ingress (IP allowlist or auth) in production.
"""

from __future__ import annotations

import os
from fastapi import FastAPI, Request
from starlette.responses import Response


def _path_group(path: str) -> str:
    """Group URLs to limit Prometheus label cardinality (drop ids after 2nd segment)."""
    parts = [p for p in (path or "").split("/") if p]
    if not parts:
        return "/"
    if parts[0] == "api":
        if len(parts) >= 2:
            return "/" + "/".join(parts[:2])
        return "/api"
    return "/" + parts[0]


def install_prometheus(app: FastAPI) -> None:
    if os.getenv("PROMETHEUS_METRICS", "").lower() not in ("1", "true", "yes"):
        return
    try:
        from prometheus_client import REGISTRY, Counter, generate_latest
    except ImportError:
        print(
            "⚠️ Startup: PROMETHEUS_METRICS=1 but prometheus_client not installed — pip install .[metrics]"
        )
        return

    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"

    requests_total = Counter(
        "ccp_http_requests_total",
        "HTTP requests (grouped path)",
        ["method", "path_group", "status_code"],
    )

    @app.middleware("http")
    async def _prometheus_http_middleware(request: Request, call_next):
        response = await call_next(request)
        try:
            pg = _path_group(request.scope.get("path", ""))
            requests_total.labels(
                request.method,
                pg,
                str(response.status_code),
            ).inc()
        except Exception:
            pass
        return response

    try:
        from services.prometheus_celery_bridge import (
            refresh_celery_redis_gauges,
            register_celery_redis_gauges,
        )

        register_celery_redis_gauges(REGISTRY)
    except Exception:
        pass

    @app.get("/metrics", include_in_schema=False)
    def _metrics_endpoint():
        try:
            refresh_celery_redis_gauges()
        except Exception:
            pass
        data = generate_latest(REGISTRY)
        return Response(data, media_type=CONTENT_TYPE_LATEST)
