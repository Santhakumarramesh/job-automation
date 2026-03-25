"""
Hard gate for supervised apply: critical profile fields before **live** LinkedIn automation.

When ``TRUTH_APPLY_HARD_GATE=1``, live runs (not ``dry_run``, not ``shadow_mode``) are blocked
if the candidate profile is not auto-apply ready. Policy already downgrades exports to
``manual_assist`` when profile is incomplete; this layer refuses to start live browser apply.

Used by ``apply_to_jobs_payload``, ``run_application`` (LinkedIn path), and Streamlit (UX hint).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


def truth_apply_hard_gate_enabled() -> bool:
    return os.getenv("TRUTH_APPLY_HARD_GATE", "").strip().lower() in ("1", "true", "yes")


def assess_truth_apply_profile(profile: Optional[dict]) -> Dict[str, Any]:
    """
    Single assessment for UI + runner: required fields, ``validate_profile`` warnings,
    and ``is_auto_apply_ready`` parity.
    """
    from services.profile_service import (
        AUTO_APPLY_REQUIRED,
        is_auto_apply_ready,
        validate_profile,
    )

    prof = dict(profile or {})
    missing = [k for k in AUTO_APPLY_REQUIRED if not str(prof.get(k) or "").strip()]
    warnings = validate_profile(prof)
    auto_ready = is_auto_apply_ready(prof)
    ok = auto_ready and not missing
    return {
        "ok": ok,
        "auto_apply_ready": auto_ready,
        "missing_required_fields": missing,
        "warnings": warnings,
    }


def truth_apply_live_blocked_message(
    profile: Optional[dict],
    *,
    dry_run: bool = False,
    shadow_mode: bool = False,
) -> Optional[str]:
    """
    If live LinkedIn apply should be blocked, return a short human message; else ``None``.

    Respects ``TRUTH_APPLY_HARD_GATE``; dry-run and shadow runs are never blocked here.
    """
    if dry_run or shadow_mode:
        return None
    if not truth_apply_hard_gate_enabled():
        return None
    a = assess_truth_apply_profile(profile)
    if a["ok"]:
        return None
    miss: List[str] = a.get("missing_required_fields") or []
    if miss:
        return (
            "Truth apply gate: profile missing required fields for live apply: "
            + ", ".join(miss)
            + ". Edit config/candidate_profile.json or unset TRUTH_APPLY_HARD_GATE."
        )
    return (
        "Truth apply gate: profile is not auto-apply ready. "
        "Edit config/candidate_profile.json or unset TRUTH_APPLY_HARD_GATE."
    )
