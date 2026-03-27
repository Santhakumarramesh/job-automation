"""
Phase 7 — User Approval Workflow
Builds approval payloads and enforces explicit approval actions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from services.apply_queue_service import (
    approve_job,
    hold_job,
    reject_job,
    send_back_for_resume_review,
    get_item_by_id,
)
from services.resume_package_service import load_package
from services.resume_upload_binding import bind_approved_resume


def build_review_payload(item: dict, package: Optional[dict] = None) -> dict:
    package = package or {}
    fit_reasons = item.get("fit_reasons", [])
    unsupported = item.get("unsupported_requirements", [])
    blockers = item.get("hard_blockers", [])
    review_fields = item.get("review_fields", []) or []
    blocker_fields = item.get("blocker_fields", []) or []

    safe_to_submit = bool(item.get("safe_to_submit", 0)) and not blockers and not blocker_fields
    safe_summary = "safe_to_submit" if safe_to_submit else "review_required"

    resume_preview = {
        "resume_path": package.get("resume_path", item.get("resume_path", "")),
        "rendered_pdf_path": package.get("rendered_pdf_path", ""),
        "template_id": package.get("template_id", ""),
        "page_count": package.get("page_count", 0),
        "layout_status": package.get("layout_status", ""),
    }

    return {
        "job": {
            "id": item.get("id"),
            "company": item.get("company", ""),
            "title": item.get("job_title", ""),
            "url": item.get("job_url", ""),
        },
        "fit_explanation": {
            "overall_fit_score": item.get("overall_fit_score", 0),
            "role_family": item.get("role_family", ""),
            "seniority_band": item.get("seniority_band", ""),
            "reasons": fit_reasons,
            "hard_blockers": blockers,
        },
        "ats_explanation": {
            "ats_score": item.get("ats_score", 0),
            "truth_safe_ats_ceiling": item.get("truth_safe_ats_ceiling", 0),
            "optimization_summary": item.get("optimization_summary", package.get("optimization_summary", "")),
        },
        "unsupported_requirements": unsupported,
        "risky_fields": review_fields,
        "blocker_fields": blocker_fields,
        "resume_preview": resume_preview,
        "safe_to_submit_summary": safe_summary,
    }


def approve_job_with_metadata(item_id: str, *, approved_by: str = "user") -> dict:
    item = get_item_by_id(item_id)
    if not item:
        return {"status": "error", "message": "queue item not found"}
    package = load_package(item.get("resume_version_id", "")) or {}
    approved_path = package.get("rendered_pdf_path") or item.get("resume_path", "")
    if approved_path:
        bind_approved_resume(
            item_id,
            approved_pdf_path=approved_path,
            approved_by=approved_by,
            template_id=package.get("template_id", ""),
            page_count=package.get("page_count", 0),
            layout_status=package.get("layout_status", ""),
            package_status=package.get("package_status", ""),
        )
    payload = build_review_payload(item, package)
    metadata = {
        "approved_at": datetime.now().isoformat(),
        "approved_by": approved_by,
        "approved_resume_version_id": item.get("resume_version_id", ""),
        "approved_resume_path": approved_path,
        "review_payload": payload,
    }
    approve_job(item_id, approval_metadata=metadata)
    return {"status": "ok", "approved": True, "approval_metadata": metadata}


def hold_job_for_review(item_id: str, notes: str = "") -> dict:
    hold_job(item_id, notes=notes)
    return {"status": "ok", "held": True}


def reject_job_for_apply(item_id: str, notes: str = "") -> dict:
    reject_job(item_id, notes=notes)
    return {"status": "ok", "rejected": True}


def send_back_for_regeneration(item_id: str, notes: str = "") -> dict:
    send_back_for_resume_review(item_id, notes=notes)
    return {"status": "ok", "sent_back": True}
