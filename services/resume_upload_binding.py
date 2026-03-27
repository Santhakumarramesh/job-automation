"""
Phase 8 — Resume Upload Binding
Bind approved resume versions to queue items and enforce lookup.
"""

from __future__ import annotations

from typing import Optional

from services.apply_queue_service import get_item_by_id, set_job_state
from services.resume_version_store import create_resume_version, get_resume_version


def bind_approved_resume(
    item_id: str,
    *,
    approved_pdf_path: str,
    approved_by: str = "user",
    template_id: str = "",
    page_count: int = 0,
    layout_status: str = "",
    package_status: str = "",
) -> dict:
    version = create_resume_version(
        approved_pdf_path=approved_pdf_path,
        approved_by=approved_by,
        template_id=template_id,
        page_count=page_count,
        layout_status=layout_status,
        package_status=package_status,
    )

    from services.apply_queue_service import _db
    from datetime import datetime

    with _db() as conn:
        conn.execute(
            """
            UPDATE apply_queue SET
                approved_resume_version_id=?,
                approved_resume_path=?,
                approved_at=?,
                approved_by=?,
                updated_at=?
            WHERE id=?
            """,
            (
                version["resume_version_id"],
                version["approved_pdf_path"],
                version["approved_at"],
                version["approved_by"],
                datetime.now().isoformat(),
                item_id,
            ),
        )

    return version


def get_bound_resume_for_queue_item(item_id: str) -> dict:
    item = get_item_by_id(item_id)
    if not item:
        return {"status": "error", "message": "queue item not found"}

    rid = item.get("approved_resume_version_id") or ""
    if not rid:
        return {"status": "error", "message": "approved resume version missing"}

    version = get_resume_version(rid)
    if not version:
        return {"status": "error", "message": "approved resume version not found"}

    return {"status": "ok", "version": version}


def ensure_bound_resume_or_block(item_id: str) -> dict:
    """
    Verify a queue item has a bound approved resume; if not, mark blocked.
    """
    result = get_bound_resume_for_queue_item(item_id)
    if result.get("status") != "ok":
        set_job_state(item_id, "blocked", notes=result.get("message", "missing approved resume"))
        return result
    version = result.get("version") or {}
    path = version.get("approved_pdf_path", "")
    try:
        import os

        if not path or not os.path.isfile(path):
            msg = "approved resume file missing"
            set_job_state(item_id, "blocked", notes=msg)
            return {"status": "error", "message": msg}
    except Exception:
        pass
    return result
