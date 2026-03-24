"""
Optional per-client HTTP rate limiting (in-process sliding window).

Enable with ``API_RATE_LIMIT_ENABLED=1``. Keys clients by ``request.client.host``,
or the first hop of ``X-Forwarded-For`` when ``API_RATE_LIMIT_TRUST_X_FORWARDED_FOR=1``
(only behind a trusted proxy that strips spoofed headers).

Not a substitute for edge rate limiting in production (multi-replica counts are per instance).
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


def clear_rate_limit_state_for_tests() -> None:
    """Reset in-memory counters (unit tests only)."""
    _limiter.clear()


def install_rate_limit_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def _api_rate_limit(request: Request, call_next):
        enabled, window_sec, max_requests = _rate_limit_config()
        if not enabled:
            return await call_next(request)
        path = request.scope.get("path") or ""
        if path in _EXEMPT_EXACT:
            return await call_next(request)
        ok, retry_after = _limiter.allow(_client_key(request), window_sec, max_requests)
        if ok:
            return await call_next(request)
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded", "retry_after": retry_after},
            headers={"Retry-After": str(retry_after)},
        )
