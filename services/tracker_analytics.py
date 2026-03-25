"""
Phase 4 — tracker rollups for admin / dashboards (multi-tenant observability).

Pure functions over a DataFrame so unit tests do not need DB or CSV.
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd


def _norm_col(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns or df.empty:
        return pd.Series([""] * len(df), index=df.index, dtype=str)
    return df[col].fillna("").astype(str).str.strip()


def build_admin_tracker_analytics_summary(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Build count summaries: pipeline status, submission outcome, recruiter_response,
    and cross-tabs for response rates by tracker ``status``.
    """
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
    }
