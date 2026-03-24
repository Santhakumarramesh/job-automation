"""
Phase 3.2.3 — structured artifact metadata from tracker rows.
Aggregates resume/cover paths, screenshot list, Q&A audit JSON, and optional artifacts_manifest.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Union


def _parse_json_field(raw: Union[str, None, Any], default):
    if raw is None or raw == "":
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(str(raw))
    except json.JSONDecodeError:
        return default


def build_artifact_metadata(row: dict) -> dict:
    """
    Build API-facing artifact bundle from one tracker row (CSV/DB dict).
    """
    screenshots = _parse_json_field(row.get("screenshots_path"), [])
    if not isinstance(screenshots, list):
        screenshots = []

    qa_audit = _parse_json_field(row.get("qa_audit"), {})
    if not isinstance(qa_audit, dict):
        qa_audit = {}

    manifest = _parse_json_field(row.get("artifacts_manifest"), {})
    if not isinstance(manifest, dict):
        manifest = {}

    out = {
        "resume_path": str(row.get("resume_path") or ""),
        "cover_letter_path": str(row.get("cover_letter_path") or ""),
        "screenshots": screenshots,
        "qa_audit": qa_audit,
        "artifacts_manifest": manifest,
    }
    fu = {
        "follow_up_at": str(row.get("follow_up_at") or ""),
        "follow_up_status": str(row.get("follow_up_status") or ""),
        "follow_up_note": str(row.get("follow_up_note") or ""),
    }
    if any(str(v).strip() for v in fu.values()):
        out["follow_up"] = fu
    return out
