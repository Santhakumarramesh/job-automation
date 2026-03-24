"""
Gate LinkedIn Playwright automation on the HTTP API (login + apply + Easy Apply confirm).

MCP tools keep current behavior (no env gate). REST returns 403 unless enabled.
"""

from __future__ import annotations

import os
from typing import Any, Dict


def linkedin_browser_automation_enabled() -> bool:
    return os.getenv("ATS_ALLOW_LINKEDIN_BROWSER", "").lower() in ("1", "true", "yes")


def linkedin_browser_automation_disabled_response() -> Dict[str, Any]:
    return {
        "status": "disabled",
        "message": "Set ATS_ALLOW_LINKEDIN_BROWSER=1 to enable LinkedIn browser automation on the API.",
    }
