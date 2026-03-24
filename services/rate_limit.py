"""
Optional per-client HTTP rate limiting (in-process sliding window).

Enable with ``API_RATE_LIMIT_ENABLED=1``. Keys clients by ``request.client.host``,
or the first hop of ``X-Forwarded-For`` when ``API_RATE_LIMIT_TRUST_X_FORWARDED_FOR=1``
(only behind a trusted proxy that strips spoofed headers).

Not a substitute for edge rate limiting in production (multi-replica counts are per instance).

``POST .../ats/analyze-form/live`` (and ``/api/v1/...``) can use a **separate** cap via
``API_RATE_LIMIT_LIVE_FORM_PROBE_PER_MINUTE``; that bucket applies whenever the value is a
positive integer, even if the global API limiter is disabled.

Similarly, ``POST .../ats/search-jobs`` (LinkedIn MCP bridge) can be capped with
``API_RATE_LIMIT_ATS_SEARCH_JOBS_PER_MINUTE``.

``POST .../ats/confirm-easy-apply``, ``.../ats/apply-to-jobs``, and
``.../ats/apply-to-jobs/dry-run`` share a bucket when
``API_RATE_LIMIT_LINKEDIN_BROWSER_PER_MINUTE`` is set (Playwright + login; expensive).
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple

from fastapi import FastAPI, Request
from starlette.responses import JSONResponse

_EXEMPT_EXACT = frozenset(
    {
        "/",
        "/health",
        "/ready",
        "/metrics",
        "/openapi.json",
        "/docs",
        "/redoc",
    }
)


def _rate_limit_config() -> Tuple[bool, float, int]:
    enabled = (os.getenv("API_RATE_LIMIT_ENABLED") or "").lower() in ("1", "true", "yes")
    try:
        per_minute = int(os.getenv("API_RATE_LIMIT_PER_MINUTE", "120"))
    except ValueError:
        per_minute = 120
    per_minute = max(1, min(per_minute, 100_000))
    try:
        window = float(os.getenv("API_RATE_LIMIT_WINDOW_SECONDS", "60"))
    except ValueError:
        window = 60.0
    window = max(1.0, min(window, 3600.0))
    return enabled, window, per_minute


def _client_key(request: Request) -> str:
    if (os.getenv("API_RATE_LIMIT_TRUST_X_FORWARDED_FOR") or "").lower() in ("1", "true", "yes"):
        xff = (request.headers.get("x-forwarded-for") or "").strip()
        if xff:
            return xff.split(",")[0].strip() or "unknown"
    client = request.client
    if client and client.host:
        return client.host
    return "unknown"


class _SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()

    def allow(self, key: str, window_sec: float, max_requests: int) -> Tuple[bool, int]:
        now = time.monotonic()
        cutoff = now - window_sec
        with self._lock:
            dq = self._hits[key]
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= max_requests:
                retry_after = int(max(1, window_sec - (now - dq[0])))
                return False, retry_after
            dq.append(now)
            return True, 0


_limiter = _SlidingWindowLimiter()
_limiter_live_form_probe = _SlidingWindowLimiter()
_limiter_ats_search_jobs = _SlidingWindowLimiter()
_limiter_linkedin_browser = _SlidingWindowLimiter()


def _is_live_form_probe_path(path: str) -> bool:
    return (path or "").rstrip("/").endswith("/ats/analyze-form/live")


def _is_ats_search_jobs_path(path: str) -> bool:
    return (path or "").rstrip("/").endswith("/ats/search-jobs")


def _is_linkedin_browser_ats_path(path: str) -> bool:
    p = (path or "").rstrip("/")
    return p.endswith("/ats/confirm-easy-apply") or p.endswith("/ats/apply-to-jobs/dry-run") or p.endswith(
        "/ats/apply-to-jobs"
    )


def _dedicated_bucket_config(per_minute_env: str, window_env: str) -> Tuple[float, int] | None:
    """Parse env for a path-specific limiter; ``None`` if disabled."""
    raw = (os.getenv(per_minute_env) or "").strip()
    if raw == "":
        return None
    try:
        cap = int(raw)
    except ValueError:
        return None
    if cap <= 0:
        return None
    try:
        window = float(
            os.getenv(
                window_env,
                os.getenv("API_RATE_LIMIT_WINDOW_SECONDS", "60"),
            )
        )
    except ValueError:
        window = 60.0
    window = max(1.0, min(window, 3600.0))
    return window, min(cap, 100_000)


def _live_form_probe_limit_config() -> Tuple[float, int] | None:
    return _dedicated_bucket_config(
        "API_RATE_LIMIT_LIVE_FORM_PROBE_PER_MINUTE",
        "API_RATE_LIMIT_LIVE_FORM_PROBE_WINDOW_SECONDS",
    )


def _ats_search_jobs_limit_config() -> Tuple[float, int] | None:
    return _dedicated_bucket_config(
        "API_RATE_LIMIT_ATS_SEARCH_JOBS_PER_MINUTE",
        "API_RATE_LIMIT_ATS_SEARCH_JOBS_WINDOW_SECONDS",
    )


def _linkedin_browser_limit_config() -> Tuple[float, int] | None:
    return _dedicated_bucket_config(
        "API_RATE_LIMIT_LINKEDIN_BROWSER_PER_MINUTE",
        "API_RATE_LIMIT_LINKEDIN_BROWSER_WINDOW_SECONDS",
    )


def clear_rate_limit_state_for_tests() -> None:
    """Reset in-memory counters (unit tests only)."""
    _limiter.clear()
    _limiter_live_form_probe.clear()
    _limiter_ats_search_jobs.clear()
    _limiter_linkedin_browser.clear()


def install_rate_limit_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def _api_rate_limit(request: Request, call_next):
        path = request.scope.get("path") or ""
        if path in _EXEMPT_EXACT:
            return await call_next(request)

        key = _client_key(request)
        live_cfg = _live_form_probe_limit_config()
        if _is_live_form_probe_path(path) and live_cfg is not None:
            window_sec, max_live = live_cfg
            ok, retry_after = _limiter_live_form_probe.allow(key, window_sec, max_live)
            if not ok:
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Live form probe rate limit exceeded",
                        "retry_after": retry_after,
                    },
                    headers={"Retry-After": str(retry_after)},
                )
            return await call_next(request)

        search_cfg = _ats_search_jobs_limit_config()
        if _is_ats_search_jobs_path(path) and search_cfg is not None:
            window_sec, max_s = search_cfg
            ok, retry_after = _limiter_ats_search_jobs.allow(key, window_sec, max_s)
            if not ok:
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "ATS search-jobs rate limit exceeded",
                        "retry_after": retry_after,
                    },
                    headers={"Retry-After": str(retry_after)},
                )
            return await call_next(request)

        browser_cfg = _linkedin_browser_limit_config()
        if _is_linkedin_browser_ats_path(path) and browser_cfg is not None:
            window_sec, max_b = browser_cfg
            ok, retry_after = _limiter_linkedin_browser.allow(key, window_sec, max_b)
            if not ok:
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "LinkedIn browser automation rate limit exceeded",
                        "retry_after": retry_after,
                    },
                    headers={"Retry-After": str(retry_after)},
                )
            return await call_next(request)

        enabled, window_sec, max_requests = _rate_limit_config()
        if not enabled:
            return await call_next(request)
        ok, retry_after = _limiter.allow(key, window_sec, max_requests)
        if ok:
            return await call_next(request)
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded", "retry_after": retry_after},
            headers={"Retry-After": str(retry_after)},
        )
