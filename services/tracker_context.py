"""Merge ATS labels, ceiling, address pick, and package stats into tracker rows."""

from __future__ import annotations

import json
from typing import Dict, Optional


def build_tracker_row_extras(state: Optional[dict]) -> Dict[str, str]:
    """
    Build optional tracker columns from graph state or runner metadata.
    All values are strings for CSV/SQLite compatibility.
    """
    state = state or {}
    url = str(state.get("job_url") or state.get("url") or "").strip()
    apply_u = str(state.get("apply_url") or "").strip()

    from providers.job_source import ats_metadata_for_job

    meta = ats_metadata_for_job({"url": url or apply_u, "apply_url": apply_u})

    ceiling = state.get("truth_safe_ats_ceiling")
    if ceiling is None or str(ceiling).strip() == "":
        ceiling_s = ""
    else:
        ceiling_s = str(ceiling).strip()[:16]

    addr = str(state.get("selected_address_label") or "").strip()[:200]

    pkg = state.get("package_field_stats")
    if isinstance(pkg, dict):
        pkg_s = json.dumps(pkg, ensure_ascii=False)[:8000]
    else:
        ps = str(pkg or "").strip()
        pkg_s = ps[:8000] if ps else "{}"

    return {
        "ats_provider": str(meta.get("ats_provider", "") or "")[:120],
        "ats_provider_apply_target": str(meta.get("ats_provider_apply_target", "") or "")[:120],
        "truth_safe_ats_ceiling": ceiling_s,
        "selected_address_label": addr,
        "package_field_stats": pkg_s,
    }
