"""
ATS / board adapter protocol (v1).

Live auto-submit remains LinkedIn Easy Apply only; external boards expose
manual-assist and audit-oriented hooks for future MCP/browser tooling.
"""

from __future__ import annotations

from typing import Any, Dict, Protocol, runtime_checkable


@runtime_checkable
class ATSAdapter(Protocol):
    """Per-platform behavior surface (stubs allowed in v1)."""

    @property
    def provider_id(self) -> str: ...

    def supports_auto_apply_v1(self) -> bool:
        """True only for LinkedIn jobs Easy Apply path in v1."""
        ...

    def analyze_form(self, job_url: str) -> Dict[str, Any]:
        """Future: field schema from DOM/API; v1 returns a structured placeholder."""
        ...

    def manual_assist_capabilities(self) -> list[str]:
        """Tool / workflow IDs safe for this platform in v1."""
        ...
