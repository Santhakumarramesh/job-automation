"""
Resume replacement engine: ensure the portal has the expected resume.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from services.portal_resume_state import PortalResumeState
from services.resume_portal_adapter import LinkedInEasyApplyResumeAdapter, ResumePortalAdapter


def _result(
    *,
    status: str,
    action: str,
    expected_filename: str,
    detected_filename: str,
    state: Optional[PortalResumeState],
    verified: bool,
    error: str = "",
    steps: Optional[list[str]] = None,
) -> dict:
    return {
        "status": status,
        "action": action,
        "expected_filename": expected_filename,
        "detected_filename": detected_filename,
        "state": state.as_dict() if state else {},
        "verified": bool(verified),
        "error": error or "",
        "steps": steps or [],
    }


def _audit_resume_event(action: str, context: Optional[dict], extra: Optional[dict] = None) -> None:
    try:
        from services.observability import audit_log

        ctx = context or {}
        audit_log(
            action,
            job_id=str(ctx.get("job_id") or ctx.get("queue_item_id") or ""),
            company=str(ctx.get("company") or ""),
            position=str(ctx.get("position") or ""),
            status=str(ctx.get("queue_state") or ""),
            extra={
                "job_url": str(ctx.get("job_url") or ""),
                **(extra or {}),
            },
        )
    except Exception:
        pass


async def ensure_portal_resume(
    page: Any,
    resume_path: str,
    *,
    adapter: Optional[ResumePortalAdapter] = None,
    expected_filename: Optional[str] = None,
    audit_context: Optional[dict] = None,
) -> dict:
    """
    Ensure the portal has the expected resume uploaded.

    Returns dict with status=ok/blocked and action details.
    """
    steps: list[str] = []
    if not resume_path or not os.path.isfile(resume_path):
        return _result(
            status="blocked",
            action="none",
            expected_filename=expected_filename or "",
            detected_filename="",
            state=None,
            verified=False,
            error="resume_file_missing",
            steps=steps,
        )

    adapter = adapter or LinkedInEasyApplyResumeAdapter()
    expected = expected_filename or os.path.basename(resume_path)

    try:
        state = await adapter.detect_state(page)
        steps.append("detect_state")
        if state.existing_resume_detected:
            _audit_resume_event(
                "resume_detected_existing",
                audit_context,
                extra={
                    "detected_filename": state.existing_resume_filename,
                    "can_remove": state.can_remove_existing_resume,
                    "can_replace": state.can_replace_existing_resume,
                },
            )
    except Exception as exc:
        return _result(
            status="blocked",
            action="none",
            expected_filename=expected,
            detected_filename="",
            state=None,
            verified=False,
            error=f"resume_state_detect_failed:{str(exc)[:80]}",
            steps=steps,
        )

    if not state.resume_slot_present:
        return _result(
            status="blocked",
            action="none",
            expected_filename=expected,
            detected_filename=state.existing_resume_filename,
            state=state,
            verified=False,
            error="resume_slot_not_found",
            steps=steps,
        )

    if state.existing_resume_detected and state.matches_filename(expected):
        steps.append("verify_existing")
        verified = await adapter.verify_uploaded_resume(page, expected)
        if verified:
            _audit_resume_event(
                "resume_verified",
                audit_context,
                extra={"expected_filename": expected, "detected_filename": state.existing_resume_filename},
            )
            return _result(
                status="ok",
                action="already_correct",
                expected_filename=expected,
                detected_filename=state.existing_resume_filename,
                state=state,
                verified=True,
                steps=steps,
            )
        return _result(
            status="blocked",
            action="already_correct",
            expected_filename=expected,
            detected_filename=state.existing_resume_filename,
            state=state,
            verified=False,
            error="resume_verification_failed",
            steps=steps,
        )

    had_existing = state.existing_resume_detected
    removed = False
    if had_existing:
        if state.can_remove_existing_resume:
            steps.append("remove_existing")
            removed = await adapter.remove_current_resume(page)
            if not removed:
                return _result(
                    status="blocked",
                    action="remove_failed",
                    expected_filename=expected,
                    detected_filename=state.existing_resume_filename,
                    state=state,
                    verified=False,
                    error="resume_remove_failed",
                    steps=steps,
                )
            _audit_resume_event(
                "resume_removed_existing",
                audit_context,
                extra={"detected_filename": state.existing_resume_filename},
            )
            try:
                state = await adapter.detect_state(page)
                steps.append("detect_state_after_remove")
            except Exception:
                pass
        elif not state.can_replace_existing_resume:
            return _result(
                status="blocked",
                action="replace_not_possible",
                expected_filename=expected,
                detected_filename=state.existing_resume_filename,
                state=state,
                verified=False,
                error="resume_replace_not_possible",
                steps=steps,
            )

    if not state.upload_control_found:
        return _result(
            status="blocked",
            action="upload_control_missing",
            expected_filename=expected,
            detected_filename=state.existing_resume_filename,
            state=state,
            verified=False,
            error="upload_control_not_found",
            steps=steps,
        )

    steps.append("upload_resume")
    uploaded = await adapter.upload_resume(page, resume_path)
    if not uploaded:
        return _result(
            status="blocked",
            action="upload_failed",
            expected_filename=expected,
            detected_filename=state.existing_resume_filename,
            state=state,
            verified=False,
            error="resume_upload_failed",
            steps=steps,
        )
    _audit_resume_event(
        "resume_uploaded_new",
        audit_context,
        extra={"expected_filename": expected, "resume_path": resume_path},
    )

    steps.append("verify_upload")
    verified = await adapter.verify_uploaded_resume(page, expected)
    if not verified:
        return _result(
            status="blocked",
            action="verification_failed",
            expected_filename=expected,
            detected_filename=state.existing_resume_filename,
            state=state,
            verified=False,
            error="resume_verification_failed",
            steps=steps,
        )
    _audit_resume_event(
        "resume_verified",
        audit_context,
        extra={"expected_filename": expected, "detected_filename": state.existing_resume_filename},
    )

    action = "uploaded"
    if had_existing:
        action = "removed_then_uploaded" if removed else "replaced"

    try:
        state = await adapter.detect_state(page)
    except Exception:
        pass

    return _result(
        status="ok",
        action=action,
        expected_filename=expected,
        detected_filename=state.existing_resume_filename,
        state=state,
        verified=True,
        steps=steps,
    )
