"""
Phase 13 — tracker + audit JSONL aggregates and heuristic hints.
Phase 43 — answerer_review rollups from tracker ``qa_audit`` (apply runner metadata).
"""

from __future__ import annotations

import json
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from services.observability import AUDIT_LOG_PATH


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_ats_value(raw: Any) -> Optional[float]:
    if raw is None or raw == "":
        return None
    try:
        s = str(raw).strip().replace("%", "")
        v = float(s)
        if v > 1.0 and v <= 100.0:
            return v
        if 0.0 <= v <= 1.0:
            return v * 100.0
        return min(max(v, 0.0), 100.0)
    except (TypeError, ValueError):
        return None


def _top_counts(df, col: str, limit: int = 20) -> Dict[str, int]:
    if col not in df.columns:
        return {}
    s = df[col].fillna("").astype(str).str.strip()
    s = s.replace("", "(empty)")
    vc = s.value_counts().head(limit)
    return {str(k): int(v) for k, v in vc.items()}


def _ats_summary(df) -> Dict[str, Any]:
    if "ats_score" not in df.columns:
        return {"count_numeric": 0, "mean": None, "min": None, "max": None, "missing": int(len(df))}
    vals: List[float] = []
    missing = 0
    for x in df["ats_score"]:
        p = _parse_ats_value(x)
        if p is None:
            missing += 1
        else:
            vals.append(p)
    if not vals:
        return {"count_numeric": 0, "mean": None, "min": None, "max": None, "missing": missing}
    return {
        "count_numeric": len(vals),
        "mean": round(sum(vals) / len(vals), 2),
        "min": round(min(vals), 2),
        "max": round(max(vals), 2),
        "missing": missing,
    }


def _suggestions(
    by_policy: Dict[str, int],
    by_apply_mode: Dict[str, int],
    by_submission: Dict[str, int],
) -> List[str]:
    hints: List[str] = []
    ats_skips = int(by_policy.get("skip_ats_below_threshold", 0))
    if ats_skips >= 3:
        hints.append(
            "Several policy skips are `skip_ats_below_threshold`; consider lowering the ATS bar for discovery "
            "or improving the resume before policy runs."
        )
    manual = sum(v for k, v in by_apply_mode.items() if "manual" in k.lower())
    total_modes = sum(by_apply_mode.values()) or 1
    if manual >= 5 and manual / total_modes >= 0.4:
        hints.append(
            "A large share of jobs are in manual_assist; confirm Easy Apply when you want auto-apply, "
            "or use external career-site applies by design."
        )
    failed = sum(v for k, v in by_submission.items() if "fail" in k.lower() or "skipped" in k.lower())
    if failed >= 3:
        hints.append(
            "Multiple non-success submission statuses in the tracker; check MCP apply logs and audit JSONL for patterns."
        )
    if not hints:
        hints.append("No strong automated hints yet; keep logging applications to improve trends.")
    return hints


def compute_answerer_review_insights(records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Parse ``qa_audit`` JSON on tracker rows; aggregate ``_answerer_review`` (application runner).
    """
    rows_with_block = 0
    rows_with_any_ar = 0
    field_manual = Counter()
    reason_codes = Counter()
    classified = Counter()

    for row in records:
        raw = row.get("qa_audit")
        if raw is None or raw == "":
            continue
        try:
            q = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(q, dict):
            continue
        ar = q.get("_answerer_review")
        if not ar or not isinstance(ar, dict):
            continue
        rows_with_any_ar += 1
        block = False
        for _fk, meta in ar.items():
            if not isinstance(meta, dict):
                continue
            if meta.get("manual_review_required"):
                field_manual[str(_fk)] += 1
                block = True
            for rc in meta.get("reason_codes") or []:
                reason_codes[str(rc)] += 1
            ct = meta.get("classified_type")
            if ct:
                classified[str(ct)] += 1
        if block:
            rows_with_block += 1

    return {
        "tracker_rows_with_answerer_review": rows_with_any_ar,
        "tracker_rows_with_manual_review_flag": rows_with_block,
        "manual_review_by_field": dict(field_manual.most_common(25)),
        "reason_code_counts": dict(reason_codes.most_common(30)),
        "classified_type_counts": dict(classified.most_common(15)),
    }


def compute_tracker_insights(for_user_id: Optional[str]) -> Dict[str, Any]:
    from services.application_tracker import load_applications

    df = load_applications(for_user_id=for_user_id)
    if df.empty:
        return {
            "total": 0,
            "by_submission_status": {},
            "by_apply_mode": {},
            "by_policy_reason": {},
            "by_fit_decision": {},
            "by_recruiter_response": {},
            "ats": _ats_summary(df),
            "suggestions": ["No tracker rows for this scope yet; run the pipeline or log applications first."],
        }

    by_sub = _top_counts(df, "submission_status", 25)
    by_mode = _top_counts(df, "apply_mode", 15)
    by_pol = _top_counts(df, "policy_reason", 25)
    by_fit = _top_counts(df, "fit_decision", 10)
    by_rec = _top_counts(df, "recruiter_response", 10)

    return {
        "total": int(len(df)),
        "by_submission_status": by_sub,
        "by_apply_mode": by_mode,
        "by_policy_reason": by_pol,
        "by_fit_decision": by_fit,
        "by_recruiter_response": by_rec,
        "ats": _ats_summary(df),
        "suggestions": _suggestions(by_pol, by_mode, by_sub),
    }


def _read_audit_events(max_lines: int = 2500) -> List[Dict[str, Any]]:
    path = Path(AUDIT_LOG_PATH)
    if not path.is_file():
        return []
    dq: deque[str] = deque(maxlen=max(100, min(max_lines, 50_000)))
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line:
                    dq.append(line)
    except OSError:
        return []
    out: List[Dict[str, Any]] = []
    for line in dq:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def summarize_audit_log(
    for_user_id: Optional[str],
    *,
    max_lines: int = 2500,
) -> Optional[Dict[str, Any]]:
    events = _read_audit_events(max_lines=max_lines)
    if not events:
        return None

    if for_user_id is not None:
        filtered = []
        for e in events:
            uid = (e.get("extra") or {}).get("user_id")
            if uid is not None and str(uid) == str(for_user_id):
                filtered.append(e)
        events = filtered

    by_action: Counter[str] = Counter()
    celery_outcome: Counter[str] = Counter()
    failure_class: Counter[str] = Counter()

    for e in events:
        act = str(e.get("action") or "(unknown)")
        by_action[act] += 1
        if act == "celery_task_finished":
            st = str(e.get("status") or "")
            if st:
                celery_outcome[st] += 1
            fc = (e.get("extra") or {}).get("failure_class")
            if fc:
                failure_class[str(fc)] += 1

    return {
        "events_included": len(events),
        "by_action": dict(by_action.most_common(30)),
        "celery_task_outcomes": dict(celery_outcome.most_common(20)),
        "failure_class": dict(failure_class.most_common(10)),
    }


def build_application_insights(
    for_user_id: Optional[str],
    *,
    include_audit: bool = True,
    audit_max_lines: int = 2500,
) -> Dict[str, Any]:
    from services.application_tracker import load_applications

    tracker = compute_tracker_insights(for_user_id)
    df = load_applications(for_user_id=for_user_id)
    records = df.fillna("").to_dict(orient="records")
    answerer_stats = compute_answerer_review_insights(records)

    audit = None
    if include_audit:
        audit = summarize_audit_log(for_user_id, max_lines=audit_max_lines)

    suggestions = list(tracker.get("suggestions") or [])
    if audit and audit.get("failure_class"):
        suggestions.append(
            "Recent Celery failures include classes: "
            + ", ".join(f"{k} ({v})" for k, v in list(audit["failure_class"].items())[:5])
            + " — see worker logs and task_state snapshots."
        )
    if answerer_stats.get("tracker_rows_with_manual_review_flag", 0) >= 2:
        suggestions.append(
            "Multiple tracker rows include answerer `manual_review_required` in QA audit — "
            "tune candidate_profile short_answers or keep `block_submit_on_answerer_review` enabled."
        )

    return {
        "generated_at": _now_iso(),
        "tracker": {k: v for k, v in tracker.items() if k != "suggestions"},
        "answerer_review": answerer_stats,
        "suggestions": suggestions[:14],
        "audit": audit,
    }
