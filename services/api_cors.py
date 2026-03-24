"""
Optional CORS for the FastAPI app (browser / separate-origin dashboards).

Set ``API_CORS_ORIGINS`` to a comma-separated list of origins, or ``*`` for any origin
(dev only: cannot use credentials with ``*``).

Read once at middleware install (restart required after env change).
"""

from __future__ import annotations

import os
from typing import List, Optional

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware


def parse_api_cors_origins() -> Optional[List[str]]:
    raw = (os.getenv("API_CORS_ORIGINS") or "").strip()
    if not raw:
        return None
    if raw == "*":
        return ["*"]
    out = [x.strip() for x in raw.split(",") if x.strip()]
    return out or None


def install_cors_middleware(app: FastAPI) -> None:
    origins = parse_api_cors_origins()
    if not origins:
        return
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )
