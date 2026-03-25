"""
Summaries over job-apply run result rows (MCP ``review_unmapped_fields`` / ``application_audit_report`` parity).
REST callers pass ``run_results`` as JSON; MCP tools may load the same shape from disk.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Union


def normalize_run_result_rows(data: Union[List[Any], Dict[str, Any], None]) -> List[Dict[str, Any]]:
    if data is None:
        return []
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []
    return [r for r in data if isinstance(r, dict)]


def review_unmapped_fields_payload(run_results: Union[List[Dict[str, Any]], Dict[str, Any]]) -> dict:
    data = normalize_run_result_rows(run_results)
    all_unmapped: List[str] = []
    for r in data:
        unmapped = r.get("unmapped_fields", [])
        if isinstance(unmapped, list):
            all_unmapped.extend(str(x) for x in unmapped if x is not None)
    counts = Counter(all_unmapped)
    suggestions: List[str] = []
    key_hints = {
        "sponsor": "short_answers.sponsorship",
        "salary": "salary_expectation_rule",
        "phone": "phone",
        "relocat": "relocation_preference",
        "years": "short_answers.years_*",
        "why": "short_answers.why_this_role",
    }
    for field, _ in counts.most_common(15):
        f_lower = (field or "").lower()
        for kw, prof_key in key_hints.items():
            if kw in f_lower:
                suggestions.append(f"{field} → add {prof_key}")
                break
    return {
        "status": "ok",
        "unmapped_summary": dict(counts),
        "total_unmapped": len(all_unmapped),
        "suggested_profile_keys": suggestions[:10],
    }


def application_audit_report_payload(run_results: Union[List[Dict[str, Any]], Dict[str, Any]]) -> dict:
    data = normalize_run_result_rows(run_results)
    applied = sum(1 for r in data if r.get("status") == "applied")
    skipped = sum(1 for r in data if r.get("status") == "skipped")
    failed = sum(1 for r in data if r.get("status") == "failed")
    dry_run = sum(1 for r in data if r.get("status") == "dry_run")
    shadow_yes = sum(1 for r in data if r.get("status") == "shadow_would_apply")
    shadow_no = sum(1 for r in data if r.get("status") == "shadow_would_not_apply")
    manual = sum(1 for r in data if r.get("status") == "manual_assist_ready")
    errors = [r.get("error", "") for r in data if r.get("error")]
    all_unmapped: List[str] = []
    for r in data:
        raw = r.get("unmapped_fields", []) or []
        if isinstance(raw, list):
            all_unmapped.extend(str(x) for x in raw if x is not None)
    return {
        "status": "ok",
        "applied": applied,
        "skipped": skipped,
        "failed": failed,
        "dry_run": dry_run,
        "shadow_would_apply": shadow_yes,
        "shadow_would_not_apply": shadow_no,
        "manual_assist_ready": manual,
        "fail_reasons": list(dict.fromkeys(e for e in errors if e))[:5],
        "unmapped_fields_count": len(all_unmapped),
        "unmapped_summary": dict(Counter(all_unmapped)),
    }
