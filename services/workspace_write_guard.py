"""
Phase 4 — multi-tenant hardening for workspace_id on write paths.

When ``API_ENFORCE_USER_WORKSPACE_ON_WRITES=1``, any authenticated user that has a
non-empty ``workspace_id`` (JWT claim / ``X-Workspace-Id``) may only enqueue jobs
with that same workspace on the payload. Empty client workspace is filled with the
user default. Admins are exempt unless ``API_WORKSPACE_ENFORCE_FOR_ADMIN=1``.

``API_ATS_LINKEDIN_REQUIRE_AUTH=1`` rejects the open ``demo-user`` on LinkedIn browser
ATS routes (``confirm-easy-apply``, ``apply-to-jobs``, ``apply-to-jobs/dry-run``).

Batch apply also honors per-job ``workspace_id`` / ``organization_id`` and optional
JSON ``workspace_id`` (default for all jobs) when enforcement is on; ``user_id`` is
stamped from the authenticated principal when missing (non-demo users).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, MutableMapping, Optional

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


def ats_linkedin_require_auth_enabled() -> bool:
    """When true, LinkedIn browser ATS routes reject anonymous demo-user callers."""
    return _truthy("API_ATS_LINKEDIN_REQUIRE_AUTH")


def assert_ats_linkedin_caller_allowed(user: Any) -> None:
    """
    Raise ``401`` if strict LinkedIn ATS auth is on and the principal is the open
    ``demo-user`` (no ``API_KEY`` / JWT / M2M configured path).
    """
    if not ats_linkedin_require_auth_enabled():
        return
    uid = str(getattr(user, "id", "") or "").strip()
    if uid == "demo-user":
        raise HTTPException(
            status_code=401,
            detail="LinkedIn ATS requires authentication (API_ATS_LINKEDIN_REQUIRE_AUTH=1). "
            "Send X-API-Key, Bearer JWT, or X-M2M-API-Key.",
        )


def _job_effective_workspace(
    job: MutableMapping[str, Any], default_ws: Optional[str]
) -> tuple[str, str, str]:
    """Return (workspace_id, organization_id, effective) stripped."""
    w = str(job.get("workspace_id") or "").strip()[:200]
    o = str(job.get("organization_id") or "").strip()[:200]
    d = (default_ws or "").strip()[:200] if default_ws else ""
    eff = w or o or d
    return w, o, eff


def enforce_user_workspace_on_apply_jobs(
    *,
    user: Any,
    jobs: List[Any],
    default_workspace_id: Optional[str] = None,
) -> None:
    """
    Mutate each job dict in place for tenant alignment (same rules as enqueue payload).

    - When ``API_ENFORCE_USER_WORKSPACE_ON_WRITES`` is off, no-op.
    - Optional ``default_workspace_id`` (e.g. JSON body ``workspace_id``) fills empty jobs.
    - Injects ``user_id`` on each job from ``user.id`` when the job omits ``user_id`` /
      ``authenticated_user_id`` (tracker metadata).
    """
    if not jobs:
        return
    uid = str(getattr(user, "id", "") or "").strip()
    if uid and uid != "demo-user":
        for jraw in jobs:
            if not isinstance(jraw, MutableMapping):
                continue
            ju = str(jraw.get("user_id") or jraw.get("authenticated_user_id") or "").strip()
            if not ju:
                jraw["user_id"] = uid[:240]

    if not _truthy("API_ENFORCE_USER_WORKSPACE_ON_WRITES"):
        return
    if getattr(user, "is_admin", False) and not _truthy("API_WORKSPACE_ENFORCE_FOR_ADMIN"):
        return
    uw = str(getattr(user, "workspace_id", None) or "").strip()
    if not uw:
        return
    uw = uw[:200]
    dw = (default_workspace_id or "").strip()[:200] if default_workspace_id else ""

    for jraw in jobs:
        if not isinstance(jraw, MutableMapping):
            continue
        w_raw, o_raw, eff = _job_effective_workspace(jraw, dw or None)
        if w_raw and o_raw and w_raw != o_raw:
            raise HTTPException(
                status_code=400,
                detail="A job has workspace_id and organization_id that disagree.",
            )
        if not eff:
            jraw["workspace_id"] = uw
            continue
        if eff != uw:
            raise HTTPException(
                status_code=403,
                detail="Job workspace_id does not match authenticated workspace (API_ENFORCE_USER_WORKSPACE_ON_WRITES).",
            )
        jraw["workspace_id"] = eff
