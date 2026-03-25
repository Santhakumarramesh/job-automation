"""
Phase 4 — multi-tenant hardening for workspace_id on write paths.

When ``API_ENFORCE_USER_WORKSPACE_ON_WRITES=1``, any authenticated user that has a
non-empty ``workspace_id`` (JWT claim / ``X-Workspace-Id``) may only enqueue jobs
with that same workspace on the payload. Empty client workspace is filled with the
user default. Admins are exempt unless ``API_WORKSPACE_ENFORCE_FOR_ADMIN=1``.
"""

from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import HTTPException


def _truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def _payload_workspace_candidates(payload: Dict[str, Any]) -> tuple[str, str]:
    """Return (workspace_id, organization_id) stripped; may be empty."""
    w = str(payload.get("workspace_id") or "").strip()
    o = str(payload.get("organization_id") or "").strip()
    return w[:200], o[:200]


def enforce_user_workspace_on_job_payload(*, user: Any, payload: Dict[str, Any]) -> None:
    """
    Mutate ``payload`` in place: set ``workspace_id`` from the authenticated tenant when
    allowed; raise ``HTTPException(403)`` on cross-tenant spoofing.
    """
    if not _truthy("API_ENFORCE_USER_WORKSPACE_ON_WRITES"):
        return
    if getattr(user, "is_admin", False) and not _truthy("API_WORKSPACE_ENFORCE_FOR_ADMIN"):
        return
    uw = str(getattr(user, "workspace_id", None) or "").strip()
    if not uw:
        return
    uw = uw[:200]
    w_raw, o_raw = _payload_workspace_candidates(payload)
    if w_raw and o_raw and w_raw != o_raw:
        raise HTTPException(
            status_code=400,
            detail="workspace_id and organization_id disagree; send one consistent workspace identifier.",
        )
    eff = w_raw or o_raw
    if not eff:
        payload["workspace_id"] = uw
        return
    if eff != uw:
        raise HTTPException(
            status_code=403,
            detail="workspace_id does not match authenticated workspace (API_ENFORCE_USER_WORKSPACE_ON_WRITES).",
        )
    payload["workspace_id"] = eff
