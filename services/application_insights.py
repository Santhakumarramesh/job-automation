"""
Phase 13 — tracker + audit JSONL aggregates and heuristic hints.
Phase 43 — answerer_review rollups from tracker ``qa_audit`` (apply runner metadata).
"""

from __future__ import annotations

import json
import math
from collections import Counter, deque, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from services.observability import get_audit_log_path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_safe(obj: Any) -> Any:
    """Recursively replace NaN/Inf floats so FastAPI/json.dumps never fails on tracker payloads."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    return obj


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


def _truth_ceiling_summary(df) -> Dict[str, Any]:
    col = "truth_safe_ats_ceiling"
    if col not in df.columns:
        return {"count_numeric": 0, "mean": None, "min": None, "max": None, "missing": int(len(df))}
    vals: List[float] = []
    missing = 0
    for x in df[col]:
        s = str(x).strip() if x is not None else ""
        if not s:
            missing += 1
            continue
        try:
            v = float(s.replace("%", ""))
            if 0 <= v <= 100:
                vals.append(v)
            else:
                missing += 1
        except (TypeError, ValueError):
            missing += 1
    if not vals:
        return {"count_numeric": 0, "mean": None, "min": None, "max": None, "missing": missing}
    return {
        "count_numeric": len(vals),
        "mean": round(sum(vals) / len(vals), 2),
        "min": round(min(vals), 2),
        "max": round(max(vals), 2),
        "missing": missing,
    }


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


def _norm_pipeline_val(s: str) -> str:
    t = str(s or "").strip().lower()
    return "" if t in ("", "(empty)", "none") else t


def compute_pipeline_correlations(df) -> Dict[str, Any]:
    """
    Conditional ``policy_reason`` counts for rows with meaningful interview/offer outcomes.
    """
    out: Dict[str, Any] = {
        "policy_reason_when_offer_accepted": {},
        "policy_reason_when_offer_declined": {},
        "policy_reason_when_interview_ended_negative": {},
    }
    if df.empty or "policy_reason" not in df.columns:
        return out

    if "offer_outcome" in df.columns:
        off = df["offer_outcome"].fillna("").map(_norm_pipeline_val)
        acc = off.isin(("accepted", "yes"))
        dec = off.isin(("declined", "rejected"))
        out["policy_reason_when_offer_accepted"] = _top_counts(df[acc], "policy_reason", 15)
        out["policy_reason_when_offer_declined"] = _top_counts(df[dec], "policy_reason", 15)

    if "interview_stage" in df.columns:
        stg = df["interview_stage"].fillna("").map(_norm_pipeline_val)
        neg = stg.isin(("rejected", "withdrew", "no_show"))
        out["policy_reason_when_interview_ended_negative"] = _top_counts(df[neg], "policy_reason", 15)

    return out


def _crosstab_top_pairs(
    df,
    col_a: str,
    col_b: str,
    *,
    label_a: str,
    label_b: str,
    limit: int = 32,
) -> List[Dict[str, Any]]:
    """Top (col_a, col_b) pair counts for failure / policy correlation views."""
    if df.empty or col_a not in df.columns or col_b not in df.columns:
        return []
    a = df[col_a].fillna("").astype(str).str.strip().replace("", "(empty)")
    b = df[col_b].fillna("").astype(str).str.strip().replace("", "(empty)")
    ctr: Counter[tuple[str, str]] = Counter(zip(a.tolist(), b.tolist()))
    return [
        {label_a: pair[0], label_b: pair[1], "count": n}
        for pair, n in ctr.most_common(max(1, min(limit, 80)))
    ]


def compute_shadow_insights(df) -> Dict[str, Any]:
    """
    Phase 2 — aggregate shadow-mode tracker rows (``submission_status`` / ``status``).
    Use with real **Applied** counts to reason about pilot readiness (manual cohort compare for v0).
    """
    empty = {
        "shadow_rows": 0,
        "by_shadow_submission": {},
        "shadow_would_apply_rows": 0,
        "shadow_would_not_apply_rows": 0,
        "applied_submission_rows": 0,
        "tracker_status_shadow_rows": 0,
    }
    if df is None or getattr(df, "empty", True):
        return {**empty, "note": "No rows in scope."}

    sub = (
        df["submission_status"].fillna("").astype(str).str.strip()
        if "submission_status" in df.columns
        else None
    )
    if sub is None:
        return {**empty, "note": "No submission_status column."}

    is_shadow = sub.str.startswith("Shadow", na=False)
    shadow_df = df[is_shadow]
    would_apply = int((sub == "Shadow – Would Apply").sum())
    would_not = int((sub == "Shadow – Would Not Apply").sum())
    applied_n = int((sub == "Applied").sum())

    st_shadow = 0
    if "status" in df.columns:
        st_shadow = int(
            df["status"].fillna("").astype(str).str.strip().str.lower().eq("shadow").sum()
        )

    by_sub: Dict[str, int] = {}
    if not shadow_df.empty and "submission_status" in shadow_df.columns:
        by_sub = _top_counts(shadow_df, "submission_status", 12)

    return {
        "shadow_rows": int(is_shadow.sum()),
        "by_shadow_submission": by_sub,
        "shadow_would_apply_rows": would_apply,
        "shadow_would_not_apply_rows": would_not,
        "applied_submission_rows": applied_n,
        "tracker_status_shadow_rows": st_shadow,
        "note": (
            "Compare **shadow_would_apply_rows** with **applied_submission_rows** over the same job cohort "
            "when evaluating a live pilot (v0: manual analysis)."
        ),
    }


def compute_tracker_crosstabs(df) -> Dict[str, Any]:
    """
    Pairwise counts for common tracker dimensions (submission vs policy, etc.).
    """
    return {
        "submission_status_by_policy_reason": _crosstab_top_pairs(
            df,
            "submission_status",
            "policy_reason",
            label_a="submission_status",
            label_b="policy_reason",
            limit=36,
        ),
        "submission_status_by_apply_mode": _crosstab_top_pairs(
            df,
            "submission_status",
            "apply_mode",
            label_a="submission_status",
            label_b="apply_mode",
            limit=28,
        ),
        "apply_mode_by_policy_reason": _crosstab_top_pairs(
            df,
            "apply_mode",
            "policy_reason",
            label_a="apply_mode",
            label_b="policy_reason",
            limit=28,
        ),
        "apply_mode_by_ats_provider_apply_target": _crosstab_top_pairs(
            df,
            "apply_mode",
            "ats_provider_apply_target",
            label_a="apply_mode",
            label_b="ats_provider_apply_target",
            limit=36,
        ),
        "submission_status_by_ats_provider_apply_target": _crosstab_top_pairs(
            df,
            "submission_status",
            "ats_provider_apply_target",
            label_a="submission_status",
            label_b="ats_provider_apply_target",
            limit=40,
        ),
    }


def _failure_hint_from_crosstabs(crosstabs: Dict[str, Any]) -> Optional[str]:
    """Single heuristic when failed / skipped submissions cluster on one policy reason."""
    rows = crosstabs.get("submission_status_by_policy_reason") or []
    if not rows:
        return None
    fail_kw = ("fail", "skipped", "skip", "error", "challenge", "unmapped")
    agg: defaultdict[str, int] = defaultdict(int)
    for r in rows:
        if not isinstance(r, dict):
            continue
        sub = str(r.get("submission_status") or "").lower()
        if not any(k in sub for k in fail_kw):
            continue
        pol = str(r.get("policy_reason") or "(empty)")
        agg[pol] += int(r.get("count") or 0)
    if not agg:
        return None
    top_pol, top_n = max(agg.items(), key=lambda x: x[1])
    total = sum(agg.values())
    if total >= 3 and top_n >= 2 and top_n / total >= 0.5:
        return (
            f"Most tracker rows with failed/skipped **submission_status** share policy_reason "
            f"`{top_pol}` ({top_n}/{total} in the top cross-tab slice) — inspect that policy path and MCP apply logs."
        )
    return None


def compute_tracker_insights(
    for_user_id: Optional[str],
    *,
    workspace_id: Optional[str] = None,
) -> Dict[str, Any]:
    from services.application_tracker import load_applications

    df = load_applications(for_user_id=for_user_id, workspace_id=workspace_id)
    if df.empty:
        sh_empty = compute_shadow_insights(df)
        return {
            "total": 0,
            "by_submission_status": {},
            "by_apply_mode": {},
            "by_policy_reason": {},
            "by_fit_decision": {},
            "by_recruiter_response": {},
            "by_interview_stage": {},
            "by_offer_outcome": {},
            "by_ats_provider": {},
            "by_ats_provider_apply_target": {},
            "truth_safe_ats_ceiling": _truth_ceiling_summary(df),
            "pipeline_correlations": compute_pipeline_correlations(df),
            "crosstabs": compute_tracker_crosstabs(df),
            "ats": _ats_summary(df),
            "shadow": sh_empty,
            "suggestions": ["No tracker rows for this scope yet; run the pipeline or log applications first."],
        }

    by_sub = _top_counts(df, "submission_status", 25)
    by_mode = _top_counts(df, "apply_mode", 15)
    by_pol = _top_counts(df, "policy_reason", 25)
    by_fit = _top_counts(df, "fit_decision", 10)
    by_rec = _top_counts(df, "recruiter_response", 10)
    by_iv = _top_counts(df, "interview_stage", 20)
    by_of = _top_counts(df, "offer_outcome", 20)
    pipe_corr = compute_pipeline_correlations(df)
    xtabs = compute_tracker_crosstabs(df)
    shadow_stats = compute_shadow_insights(df)
    sug = _suggestions(by_pol, by_mode, by_sub)
    xh = _failure_hint_from_crosstabs(xtabs)
    if xh:
        sug = [xh] + [s for s in sug if s != xh][:12]
    swa = int(shadow_stats.get("shadow_would_apply_rows") or 0)
    asn = int(shadow_stats.get("applied_submission_rows") or 0)
    if swa >= 5 and asn <= 1:
        sug.insert(
            0,
            "Several **Shadow – Would Apply** rows but few **Applied** submissions — review blockers before a live pilot, "
            "or run shadow and live on the same export cohort to compare.",
        )

    return {
        "total": int(len(df)),
        "by_submission_status": by_sub,
        "by_apply_mode": by_mode,
        "by_policy_reason": by_pol,
        "by_fit_decision": by_fit,
        "by_recruiter_response": by_rec,
        "by_interview_stage": by_iv,
        "by_offer_outcome": by_of,
        "by_ats_provider": _top_counts(df, "ats_provider", 20),
        "by_ats_provider_apply_target": _top_counts(df, "ats_provider_apply_target", 20),
        "truth_safe_ats_ceiling": _truth_ceiling_summary(df),
        "pipeline_correlations": pipe_corr,
        "crosstabs": xtabs,
        "ats": _ats_summary(df),
        "shadow": shadow_stats,
        "suggestions": sug,
    }


def _read_audit_events(max_lines: int = 2500) -> List[Dict[str, Any]]:
    path = get_audit_log_path()
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
    workspace_id: Optional[str] = None,
    include_audit: bool = True,
    audit_max_lines: int = 2500,
) -> Dict[str, Any]:
    from services.application_tracker import load_applications

    tracker = compute_tracker_insights(for_user_id, workspace_id=workspace_id)
    df = load_applications(for_user_id=for_user_id, workspace_id=workspace_id)
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
    pc = (tracker.get("pipeline_correlations") or {}) if isinstance(tracker, dict) else {}
    acc_n = sum((pc.get("policy_reason_when_offer_accepted") or {}).values())
    if acc_n >= 2:
        suggestions.append(
            f"Recorded **{acc_n}** accepted offer(s); review `pipeline_correlations.policy_reason_when_offer_accepted` "
            "to see which apply-policy paths correlate with wins."
        )
    xt = (tracker.get("crosstabs") or {}) if isinstance(tracker, dict) else {}
    if isinstance(xt, dict) and any(xt.values()):
        suggestions.append(
            "See `tracker.crosstabs` for **submission_status × policy_reason** (and related pairs) to spot failure clusters."
        )

    return _json_safe(
        {
            "generated_at": _now_iso(),
            "tracker": {k: v for k, v in tracker.items() if k != "suggestions"},
            "answerer_review": answerer_stats,
            "suggestions": suggestions[:14],
            "audit": audit,
        }
    )
