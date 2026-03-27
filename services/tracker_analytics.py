"""
Phase 4 — tracker rollups for admin / dashboards (multi-tenant observability).

Pure functions over a DataFrame so unit tests do not need DB or CSV.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

# Slim columns for admin BI export (no full job_description / qa_audit blobs).
TRACKER_ANALYTICS_BI_COLUMNS: List[str] = [
    "id",
    "user_id",
    "workspace_id",
    "source",
    "job_id",
    "company",
    "position",
    "status",
    "submission_status",
    "recruiter_response",
    "applied_at",
    "job_state",
    "apply_mode",
    "policy_reason",
    "fit_decision",
    "fit_state",
    "package_state",
    "approval_state",
    "queue_state",
    "runner_state",
    "final_state",
    "ats_score",
    "follow_up_at",
    "follow_up_status",
    "interview_stage",
    "offer_outcome",
]


def _by_applied_iso_week(df: pd.DataFrame) -> tuple[Dict[str, int], int]:
    """
    Bucket rows by ISO week of ``applied_at`` (UTC). Keys: ``YYYY-Www`` (week zero-padded).

    Returns ``(counts_by_week, rows_with_parseable_applied_at)``.
    """
    if df.empty or "applied_at" not in df.columns:
        return {}, 0
    ts = pd.to_datetime(df["applied_at"], errors="coerce", utc=True)
    valid = ts.notna()
    n_parse = int(valid.sum())
    if n_parse == 0:
        return {}, 0
    t_ok = ts[valid]
    try:
        iso = t_ok.dt.isocalendar()
        keys = iso.year.astype(str) + "-W" + iso.week.astype(str).str.zfill(2)
    except (AttributeError, TypeError, ValueError):
        return {}, n_parse
    vc = keys.value_counts().sort_index()
    return {str(k): int(v) for k, v in vc.items()}, n_parse


def _by_applied_month_utc(df: pd.DataFrame) -> Dict[str, int]:
    """Bucket rows by calendar month of ``applied_at`` (UTC). Keys: ``YYYY-MM``."""
    if df.empty or "applied_at" not in df.columns:
        return {}
    ts = pd.to_datetime(df["applied_at"], errors="coerce", utc=True)
    valid = ts.notna()
    if not bool(valid.any()):
        return {}
    t_ok = ts[valid]
    try:
        keys = t_ok.dt.strftime("%Y-%m")
    except (AttributeError, TypeError, ValueError):
        return {}
    vc = keys.value_counts().sort_index()
    return {str(k): int(v) for k, v in vc.items()}


def _timeseries_v0_from_buckets(
    by_week: Dict[str, int], by_month: Dict[str, int], n_parse: int
) -> Dict[str, Any]:
    return {
        "note": (
            "Buckets use parseable ``applied_at`` in UTC. Rows without a parseable "
            "``applied_at`` are omitted from week/month series (see ``rows_with_parseable_applied_at`` on the parent summary)."
        ),
        "by_applied_iso_week_utc": dict(by_week),
        "by_applied_month_utc": dict(by_month),
        "rows_in_time_buckets": int(n_parse),
    }


def slim_tracker_rows_for_bi_export(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Return list of dicts with fixed keys; stringified cells, no large JSON columns."""
    if df is None or getattr(df, "empty", True):
        return []
    out: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        rec: Dict[str, Any] = {}
        for c in TRACKER_ANALYTICS_BI_COLUMNS:
            if c not in df.columns:
                rec[c] = ""
                continue
            v = row.get(c)
            if v is None or (isinstance(v, float) and pd.isna(v)):
                rec[c] = ""
            else:
                rec[c] = str(v).strip()
        out.append(rec)
    return out


def _norm_col(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns or df.empty:
        return pd.Series([""] * len(df), index=df.index, dtype=str)
    return df[col].fillna("").astype(str).str.strip()


def build_admin_tracker_analytics_summary(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Build count summaries: pipeline status, submission outcome, recruiter_response,
    and cross-tabs for response rates by tracker ``status``.
    """
    from services.application_insights import compute_shadow_insights

    shadow_metrics_v0 = compute_shadow_insights(df)
    if df is None or len(df) == 0:
        return {
            "row_count": 0,
            "by_status": {},
            "by_submission_status": {},
            "by_recruiter_response": {},
            "status_by_recruiter_response": {},
            "unique_user_ids": 0,
            "unique_workspace_ids": 0,
            "applied_row_count": 0,
            "applied_by_recruiter_response": {},
            "by_applied_iso_week": {},
            "rows_with_parseable_applied_at": 0,
            "by_job_state": {},
            "shadow_metrics_v0": shadow_metrics_v0,
            "timeseries_v0": _timeseries_v0_from_buckets({}, {}, 0),
        }

    st = _norm_col(df, "status")
    ss = _norm_col(df, "submission_status")
    rr = _norm_col(df, "recruiter_response")

    def _counts(series: pd.Series) -> Dict[str, int]:
        s = series.replace("", "(empty)")
        vc = s.value_counts().sort_index()
        return {str(k): int(v) for k, v in vc.items()}

    x = pd.DataFrame({"status": st.replace("", "(empty)"), "recruiter_response": rr.replace("", "(empty)")})
    status_by_rr: Dict[str, Dict[str, int]] = {}
    for sname, g in x.groupby("status", sort=True):
        status_by_rr[str(sname)] = _counts(g["recruiter_response"])

    uid = _norm_col(df, "user_id")
    wid = _norm_col(df, "workspace_id")
    unique_users = int(uid[uid != ""].nunique())
    unique_ws = int(wid[wid != ""].nunique())

    is_applied = (st.str.lower() == "applied") | (ss == "Applied")
    applied_row_count = int(is_applied.sum())
    sub = df.loc[is_applied]
    applied_by_rr = _counts(_norm_col(sub, "recruiter_response")) if len(sub) else {}

    by_week, n_applied_ts = _by_applied_iso_week(df)
    by_month = _by_applied_month_utc(df)

    if "job_state" in df.columns and len(df):
        by_js = _counts(_norm_col(df, "job_state").replace("", "(empty)"))
    else:
        by_js = {}

    def _maybe_counts(col: str) -> Dict[str, int]:
        if col in df.columns and len(df):
            return _counts(_norm_col(df, col).replace("", "(empty)"))
        return {}

    # Lifecycle dimensions (Phase 11)
    by_fit_state = _maybe_counts("fit_state") or _maybe_counts("fit_decision")
    by_package_state = _maybe_counts("package_state")
    by_approval_state = _maybe_counts("approval_state")
    by_queue_state = _maybe_counts("queue_state")
    by_runner_state = _maybe_counts("runner_state")
    by_final_state = _maybe_counts("final_state")

    return {
        "row_count": int(len(df)),
        "by_status": _counts(st.replace("", "(empty)")),
        "by_submission_status": _counts(ss.replace("", "(empty)")),
        "by_recruiter_response": _counts(rr.replace("", "(empty)")),
        "status_by_recruiter_response": status_by_rr,
        "unique_user_ids": unique_users,
        "unique_workspace_ids": unique_ws,
        "applied_row_count": applied_row_count,
        "applied_by_recruiter_response": applied_by_rr,
        "by_applied_iso_week": by_week,
        "rows_with_parseable_applied_at": n_applied_ts,
        "by_job_state": by_js,
        "by_fit_state": by_fit_state,
        "by_package_state": by_package_state,
        "by_approval_state": by_approval_state,
        "by_queue_state": by_queue_state,
        "by_runner_state": by_runner_state,
        "by_final_state": by_final_state,
        "shadow_metrics_v0": shadow_metrics_v0,
        "timeseries_v0": _timeseries_v0_from_buckets(by_week, by_month, n_applied_ts),
    }
