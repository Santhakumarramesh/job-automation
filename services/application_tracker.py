"""
Application tracker. Logs submissions with richer schema.
Supports: source, job_url, apply_url, submission_status, screenshots, Q&A audit.
Backward compatible with existing job_applications.csv.
Set TRACKER_USE_DB=1 to use SQLite (Phase 2 production mode).
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

# Project root (this file lives in services/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
APPLICATION_FILE = _PROJECT_ROOT / "job_applications.csv"

USE_DB = os.getenv("TRACKER_USE_DB", "").lower() in ("1", "true", "yes")

# Rich schema columns (Phase 6+)
TRACKER_COLUMNS = [
    "id",
    "source",           # apify, linkedin_mcp, url
    "job_id",
    "job_url",
    "apply_url",
    "company",
    "position",
    "status",           # Applied, Interviewing, Offer, Rejected
    "submission_status",  # Applied, Manual Assist Ready, Skipped – Low Fit, Skipped – Unsupported Requirements, Dry Run Complete, Failed – Login Challenge, Failed – Form Unmapped
    "easy_apply_confirmed",
    "apply_mode",       # auto_easy_apply, manual_assist, skip
    "policy_reason",    # stable code from policy_service.decide_apply_mode_with_reason
    "fit_decision",
    "ats_score",
    "resume_path",
    "cover_letter_path",
    "job_description",
    "applied_at",
    "recruiter_response",  # Pending, positive, negative
    "screenshots_path",    # JSON list
    "qa_audit",           # JSON
    "artifacts_manifest",  # Phase 3.2.3 — JSON: S3 URIs, run ids, extra paths
    "retry_state",        # For failed
    "user_id",            # Phase 3.1.2 — scope rows per authenticated user
    "workspace_id",       # Phase 4.1.2 — org / workspace (optional filter)
    "follow_up_at",       # Phase 12 — ISO 8601 when to follow up (empty = none)
    "follow_up_status",   # pending | done | snoozed | dismissed | empty
    "follow_up_note",     # free text reminder
    "interview_stage",    # Phase 13+ — pipeline: none, scheduled, completed, advanced, rejected, withdrew, no_show
    "offer_outcome",      # none, pending, extended, accepted, declined, ghosted
    "ats_provider",
    "ats_provider_apply_target",
    "truth_safe_ats_ceiling",
    "selected_address_label",
    "package_field_stats",
    "application_decision",  # JSON: v0.1 decision payload (see application_decision.py)
    "job_state",  # Indexed copy of decision job_state (skip, manual_assist, safe_auto_apply, blocked, …)
]

# Legacy columns for backward compat
LEGACY_COLUMNS = ["Date Applied", "Company", "Position", "Status", "Resume Path", "Cover Letter Path", "Job Description"]


def _application_decision_cell_for_state(state: dict) -> str:
    try:
        from services.application_decision import application_decision_json_for_tracker_job

        job = {
            "url": str(state.get("job_url") or ""),
            "apply_url": str(state.get("apply_url") or ""),
            "company": str(state.get("target_company") or ""),
            "title": str(state.get("target_position") or ""),
            "description": str(state.get("job_description") or ""),
            "easy_apply_confirmed": bool(state.get("easy_apply_confirmed", False)),
            "fit_decision": str(state.get("fit_decision") or ""),
            "ats_score": state.get("final_ats_score", state.get("initial_ats_score")),
            "unsupported_requirements": state.get("unsupported_requirements") or [],
        }
        br = state.get("blocked_reason")
        br_s = str(br).strip()[:500] if br else None
        return application_decision_json_for_tracker_job(
            job,
            master_resume_text=str(state.get("master_resume_text") or ""),
            blocked_reason=br_s,
        )
    except Exception:
        return ""


def _application_decision_cell_from_run(run_result, job_metadata: dict) -> str:
    try:
        from services.application_decision import application_decision_json_for_tracker_job

        meta = dict(job_metadata or {})
        job = {
            "url": str(run_result.job_url or meta.get("job_url") or ""),
            "apply_url": str(meta.get("apply_url") or run_result.job_url or ""),
            "company": str(run_result.company or meta.get("company") or ""),
            "title": str(
                run_result.position or meta.get("title") or meta.get("position") or ""
            ),
            "description": str(meta.get("description") or meta.get("job_description") or ""),
            "easy_apply_confirmed": bool(meta.get("easy_apply_confirmed", False)),
            "fit_decision": str(meta.get("fit_decision") or ""),
            "ats_score": meta.get("ats_score", meta.get("final_ats_score")),
            "unsupported_requirements": meta.get("unsupported_requirements") or [],
        }
        br = meta.get("blocked_reason")
        if br:
            br_s = str(br).strip()[:500]
        elif getattr(run_result, "status", "") == "failed" and getattr(
            run_result, "error", None
        ):
            br_s = str(run_result.error).strip()[:500]
        else:
            br_s = None
        return application_decision_json_for_tracker_job(job, blocked_reason=br_s)
    except Exception:
        return ""


def _artifacts_manifest_cell(value) -> str:
    """Serialize artifacts_manifest for DB/CSV (JSON object string)."""
    if value is None or value == "":
        return "{}"
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return "{}"
        try:
            json.loads(s)
            return s[:8000]
        except json.JSONDecodeError:
            return json.dumps({"raw": s[:2000]})
    if isinstance(value, dict):
        return json.dumps(value)[:8000]
    return json.dumps({"value": str(value)})[:8000]


def _ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure all TRACKER_COLUMNS exist. Migrate from legacy if needed."""
    if df.empty:
        return pd.DataFrame(columns=TRACKER_COLUMNS)
    # Legacy format: merge into new schema
    legacy_map = {
        "Date Applied": "applied_at",
        "Company": "company",
        "Position": "position",
        "Status": "status",
        "Resume Path": "resume_path",
        "Cover Letter Path": "cover_letter_path",
        "Job Description": "job_description",
    }
    for old, new in legacy_map.items():
        if old in df.columns and new not in df.columns:
            df[new] = df[old]
    for col in TRACKER_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df.reindex(columns=TRACKER_COLUMNS, fill_value="")


def initialize_tracker():
    """Creates the CSV file or DB schema."""
    if USE_DB:
        try:
            from services.tracker_db import initialize_tracker_db
            initialize_tracker_db()
        except ImportError:
            pass
    if not USE_DB and not APPLICATION_FILE.exists():
        df = pd.DataFrame(columns=TRACKER_COLUMNS)
        df.to_csv(APPLICATION_FILE, index=False)


def log_application(state: dict):
    """Logs a processed job application. Accepts graph state."""
    initialize_tracker()
    from services.tracker_context import build_tracker_row_extras
    from services.application_decision import extract_job_state_from_decision_json

    _decision_cell = _application_decision_cell_for_state(state)
    row = {
        "id": str(uuid.uuid4()),
        "source": state.get("job_source", "url"),
        "job_id": state.get("job_id", ""),
        "job_url": state.get("job_url", ""),
        "apply_url": state.get("apply_url", ""),
        "company": state.get("target_company", "N/A"),
        "position": state.get("target_position", "N/A"),
        "status": "Applied",
        "submission_status": "submitted",
        "easy_apply_confirmed": state.get("easy_apply_confirmed", ""),
        "apply_mode": state.get("apply_mode", ""),
        "policy_reason": str(state.get("policy_reason", "") or ""),
        "fit_decision": state.get("fit_decision", ""),
        "ats_score": state.get("final_ats_score", state.get("initial_ats_score", "")),
        "resume_path": state.get("final_pdf_path", ""),
        "cover_letter_path": state.get("cover_letter_pdf_path", ""),
        "job_description": state.get("job_description", ""),
        "applied_at": datetime.now().isoformat(),
        "recruiter_response": "Pending",
        "screenshots_path": "",
        "qa_audit": "",
        "artifacts_manifest": _artifacts_manifest_cell(state.get("artifacts_manifest")),
        "retry_state": "",
        "user_id": str(
            state.get("user_id")
            or state.get("authenticated_user_id")
            or ""
        ).strip(),
        "workspace_id": str(
            state.get("workspace_id") or state.get("organization_id") or ""
        ).strip()[:200],
        "follow_up_at": str(state.get("follow_up_at", "") or ""),
        "follow_up_status": str(state.get("follow_up_status", "") or ""),
        "follow_up_note": str(state.get("follow_up_note", "") or ""),
        "interview_stage": str(state.get("interview_stage", "") or ""),
        "offer_outcome": str(state.get("offer_outcome", "") or ""),
        "application_decision": _decision_cell,
        "job_state": extract_job_state_from_decision_json(_decision_cell),
    }
    row.update(build_tracker_row_extras(state))
    if USE_DB:
        try:
            from services.tracker_db import log_application_db
            log_application_db(row)
            print(f"✅ Application for {state.get('target_company')} logged in tracker.")
            return state
        except ImportError:
            pass
    df = load_applications()
    df = _ensure_columns(df)
    new_row = pd.DataFrame([row])
    new_row = new_row.reindex(columns=TRACKER_COLUMNS, fill_value="")
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(APPLICATION_FILE, index=False)
    print(f"✅ Application for {state.get('target_company')} logged in tracker.")
    return state


def _submission_status_for_run_result(run_result) -> str:
    """Human-readable submission_status from runner status + error text."""
    st = str(getattr(run_result, "status", "") or "")
    err = str(getattr(run_result, "error", "") or "")
    el = err.lower()
    if st == "applied":
        return "Applied"
    if st == "manual_assist_ready":
        return "Manual Assist Ready"
    if st == "dry_run":
        return "Dry Run Complete"
    if st == "shadow_would_apply":
        return "Shadow – Would Apply"
    if st == "shadow_would_not_apply":
        return "Shadow – Would Not Apply"
    if st == "failed":
        if "checkpoint" in el or "challenge" in el or "verification" in el:
            return "Failed – Login Challenge"
        return "Failed – Form Unmapped"
    if st == "skipped":
        if el.strip() == "no_url" or el.startswith("no_url"):
            return "Skipped – No URL"
        if "easy_apply_only" in el or (
            "external ats" in el and "not processed" in el
        ):
            return "Skipped – External ATS"
        if el.startswith("policy_blocked") or "policy_blocked" in el:
            if "unsupported_requirements" in el:
                return "Skipped – Unsupported Requirements"
            if "ats_score" in el:
                return "Skipped – Low ATS"
            if "fit_decision" in el:
                return "Skipped – Low Fit"
            return "Skipped – Policy"
        if el.startswith("autonomy:") or "pilot_submit_only" in el:
            return "Skipped – Autonomy Gate"
        return "Skipped – Low Fit"
    return st if st else "Unknown"


def build_runner_tracker_metadata(job: dict, **extra: Any) -> dict:
    """
    Policy + job fields for ``log_application_from_result`` (MCP batch apply, CLI).
    Pass optional overrides via keyword args (e.g. ``user_id``, ``workspace_id``).
    """
    from services.policy_service import policy_from_exported_job

    j = job if isinstance(job, dict) else {}
    mode, reason = policy_from_exported_job(j)
    meta = {
        "job_id": j.get("job_id", ""),
        "fit_decision": j.get("fit_decision", ""),
        "ats_score": j.get("ats_score", j.get("final_ats_score")),
        "apply_mode": mode,
        "policy_reason": reason,
        "easy_apply_confirmed": j.get("easy_apply_confirmed"),
        "description": (j.get("description", "") or "")[:2000],
        "unsupported_requirements": j.get("unsupported_requirements") or [],
        "apply_url": j.get("apply_url") or j.get("applyUrl") or "",
    }
    u_row = str(j.get("user_id") or j.get("authenticated_user_id") or "").strip()
    if u_row:
        meta["user_id"] = u_row[:240]
    w_row = str(j.get("workspace_id") or j.get("organization_id") or "").strip()
    if w_row:
        meta["workspace_id"] = w_row[:200]
    for k, v in extra.items():
        if v is not None:
            meta[k] = v
    return meta


def log_runner_result_to_tracker(
    job: dict,
    run_result,
    resume_path: str = "",
    cover_path: str = "",
    **metadata_overrides: Any,
) -> Optional[str]:
    """
    Log any ApplicationRunner outcome (applied, skipped, failed, dry_run, manual_assist_ready).
    Swallows errors so automation never fails on tracker I/O.
    """
    try:
        meta = build_runner_tracker_metadata(job, **metadata_overrides)
        return log_application_from_result(
            run_result,
            resume_path=resume_path,
            cover_path=cover_path,
            job_metadata=meta,
        )
    except Exception:
        return None


def log_application_from_result(run_result, resume_path: str = "", cover_path: str = "", job_metadata: dict = None):
    """
    Log from ApplicationRunner RunResult. Used by scripts/apply_linkedin_jobs.py.
    job_metadata: optional dict with fit_decision, ats_score, apply_mode, easy_apply_confirmed, unsupported_requirements.
    """
    initialize_tracker()
    job_metadata = job_metadata or {}
    from services.tracker_context import build_tracker_row_extras
    from services.application_decision import extract_job_state_from_decision_json

    screenshots_json = json.dumps(run_result.screenshot_paths) if run_result.screenshot_paths else ""
    qa_combined = dict(run_result.qa_audit) if run_result.qa_audit else {}
    ar = getattr(run_result, "answerer_review", None) or {}
    if ar:
        qa_combined["_answerer_review"] = ar
    qa_json = json.dumps(qa_combined) if qa_combined else ""

    _decision_cell = _application_decision_cell_from_run(run_result, job_metadata)
    row = {
        "id": str(uuid.uuid4()),
        "source": "linkedin_mcp",
        "job_id": job_metadata.get("job_id", ""),
        "job_url": run_result.job_url,
        "apply_url": run_result.job_url,
        "company": run_result.company,
        "position": run_result.position,
        "status": (
            "Applied"
            if run_result.status == "applied"
            else (
                "Interviewing"
                if run_result.status == "manual_assist_ready"
                else (
                    "Shadow"
                    if run_result.status
                    in ("shadow_would_apply", "shadow_would_not_apply")
                    else "Rejected"
                )
            )
        ),
        "submission_status": _submission_status_for_run_result(run_result),
        "easy_apply_confirmed": job_metadata.get("easy_apply_confirmed", ""),
        "apply_mode": job_metadata.get("apply_mode", ""),
        "policy_reason": str(job_metadata.get("policy_reason", "") or ""),
        "fit_decision": job_metadata.get("fit_decision", ""),
        "ats_score": job_metadata.get("ats_score", job_metadata.get("final_ats_score", "")),
        "resume_path": resume_path,
        "cover_letter_path": cover_path,
        "job_description": job_metadata.get("description", ""),
        "applied_at": run_result.applied_at or datetime.now().isoformat(),
        "recruiter_response": "Pending",
        "screenshots_path": screenshots_json,
        "qa_audit": qa_json,
        "artifacts_manifest": _artifacts_manifest_cell(job_metadata.get("artifacts_manifest")),
        "retry_state": "",
        "user_id": str(job_metadata.get("user_id", "") or "").strip(),
        "workspace_id": str(
            job_metadata.get("workspace_id") or job_metadata.get("organization_id") or ""
        ).strip()[:200],
        "follow_up_at": "",
        "follow_up_status": "",
        "follow_up_note": "",
        "interview_stage": "",
        "offer_outcome": "",
        "application_decision": _decision_cell,
        "job_state": extract_job_state_from_decision_json(_decision_cell),
    }
    merge_state = {
        "job_url": run_result.job_url,
        "apply_url": job_metadata.get("apply_url", ""),
        "truth_safe_ats_ceiling": job_metadata.get("truth_safe_ats_ceiling"),
        "selected_address_label": job_metadata.get("selected_address_label"),
        "package_field_stats": job_metadata.get("package_field_stats"),
    }
    row.update(build_tracker_row_extras(merge_state))
    if USE_DB:
        try:
            from services.tracker_db import log_application_db
            return log_application_db(row)
        except ImportError:
            pass
    df = load_applications()
    df = _ensure_columns(df)
    new_row = pd.DataFrame([row])
    new_row = new_row.reindex(columns=TRACKER_COLUMNS, fill_value="")
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(APPLICATION_FILE, index=False)
    return row["id"]


def resolve_workspace_list_filter(
    query_workspace_id: Optional[str],
    user_default_workspace_id: Optional[str],
) -> Optional[str]:
    """
    If ``query_workspace_id`` is not None (query param was sent), use stripped value
    or None when empty (no workspace filter). If the param was omitted (None), fall
    back to the authenticated user's default workspace (JWT claim / header).
    """
    if query_workspace_id is not None:
        q = str(query_workspace_id).strip()
        return q if q else None
    u = (user_default_workspace_id or "").strip()
    return u if u else None


def load_applications(
    for_user_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> pd.DataFrame:
    """
    Load logged applications. If for_user_id is set, return only rows for that user
    (empty user_id rows are excluded — use for_user_id=None for admin / Streamlit local).
    If workspace_id is set, keep only rows with that exact workspace_id column value.
    """
    initialize_tracker()
    if USE_DB:
        try:
            from services.tracker_db import load_applications_db
            df = load_applications_db()
        except ImportError:
            df = None
        if df is not None:
            out = _filter_by_user_id(df, for_user_id)
            return _filter_by_workspace_id(out, workspace_id)
    try:
        df = pd.read_csv(APPLICATION_FILE)
        df = _ensure_columns(df)
        out = _filter_by_user_id(df, for_user_id)
        return _filter_by_workspace_id(out, workspace_id)
    except (pd.errors.EmptyDataError, Exception):
        return pd.DataFrame(columns=TRACKER_COLUMNS)


def _filter_by_user_id(df: pd.DataFrame, for_user_id: Optional[str]) -> pd.DataFrame:
    if for_user_id is None or str(for_user_id).strip() == "":
        return df
    uid = str(for_user_id).strip()
    if "user_id" not in df.columns:
        return df.iloc[0:0].copy()
    col = df["user_id"].fillna("").astype(str)
    return df[col == uid].copy()


def _filter_by_workspace_id(df: pd.DataFrame, workspace_id: Optional[str]) -> pd.DataFrame:
    if not workspace_id or not str(workspace_id).strip():
        return df
    if df.empty or "workspace_id" not in df.columns:
        return df.iloc[0:0].copy()
    w = str(workspace_id).strip()
    col = df["workspace_id"].fillna("").astype(str)
    return df[col == w].copy()


def get_application_row_by_job_id(
    job_id: str,
    for_user_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> Optional[dict]:
    """
    Return one tracker row as dict for the given job_id, scoped by for_user_id
    (same semantics as load_applications: None = all users).
    """
    if not str(job_id).strip():
        return None
    df = load_applications(for_user_id=for_user_id, workspace_id=workspace_id)
    if df.empty or "job_id" not in df.columns:
        return None
    j = str(job_id).strip()
    m = df[df["job_id"].fillna("").astype(str) == j]
    if m.empty:
        return None
    row = m.iloc[0].fillna("").to_dict()
    return row


def update_follow_up_for_row(
    row_id: str,
    scope_user_id: Optional[str],
    updates: dict,
) -> bool:
    """
    PATCH follow_up_* fields. scope_user_id None skips user_id check (demo/admin).
    """
    from services.tracker_db import FOLLOW_UP_COLUMN_SET, update_application_follow_up_partial

    patch = {k: v for k, v in updates.items() if k in FOLLOW_UP_COLUMN_SET}
    if not patch:
        return False
    if USE_DB:
        try:
            return update_application_follow_up_partial(row_id, scope_user_id, patch)
        except ImportError:
            pass
    df = load_applications(for_user_id=None)
    df = _ensure_columns(df)
    rid = str(row_id).strip()
    m = df["id"].astype(str) == rid
    if not m.any():
        return False
    idx = int(df.index[m][0])
    if scope_user_id is not None:
        row_uid = str(df.at[idx, "user_id"] or "").strip()
        if row_uid != str(scope_user_id).strip():
            return False
    for col in ("follow_up_at", "follow_up_status", "follow_up_note"):
        if col in df.columns:
            df[col] = df[col].astype(object)
    for k, v in patch.items():
        if v is None:
            df.at[idx, k] = ""
        else:
            df.at[idx, k] = str(v).strip() if isinstance(v, str) else v
    df.to_csv(APPLICATION_FILE, index=False)
    return True


def update_pipeline_for_row(
    row_id: str,
    scope_user_id: Optional[str],
    updates: dict,
) -> bool:
    """PATCH interview_stage / offer_outcome. scope_user_id None skips user_id check (demo/admin)."""
    from services.tracker_db import PIPELINE_COLUMN_SET, update_application_pipeline_partial

    patch = {k: v for k, v in updates.items() if k in PIPELINE_COLUMN_SET}
    if not patch:
        return False
    if USE_DB:
        try:
            return update_application_pipeline_partial(row_id, scope_user_id, patch)
        except ImportError:
            pass
    df = load_applications(for_user_id=None)
    df = _ensure_columns(df)
    rid = str(row_id).strip()
    m = df["id"].astype(str) == rid
    if not m.any():
        return False
    idx = int(df.index[m][0])
    if scope_user_id is not None:
        row_uid = str(df.at[idx, "user_id"] or "").strip()
        if row_uid != str(scope_user_id).strip():
            return False
    for col in ("interview_stage", "offer_outcome"):
        if col in df.columns:
            df[col] = df[col].astype(object)
    for k, v in patch.items():
        if v is None:
            df.at[idx, k] = ""
        else:
            df.at[idx, k] = str(v).strip() if isinstance(v, str) else v
    df.to_csv(APPLICATION_FILE, index=False)
    return True


def delete_applications_for_user(user_id: str) -> int:
    """
    Remove all tracker rows for ``user_id`` (exact match on ``user_id`` column).

    Returns the number of rows removed. Phase 4.4.2 — admin / compliance hook.
    """
    uid = str(user_id or "").strip()
    if not uid:
        return 0
    initialize_tracker()
    if USE_DB:
        try:
            from services.tracker_db import delete_applications_by_user_id

            return int(delete_applications_by_user_id(uid))
        except ImportError:
            pass
    df = load_applications(for_user_id=None)
    df = _ensure_columns(df)
    if df.empty or "user_id" not in df.columns:
        return 0
    col = df["user_id"].fillna("").astype(str)
    before = len(df)
    df2 = df[col != uid].copy()
    removed = before - len(df2)
    if removed:
        df2.to_csv(APPLICATION_FILE, index=False)
    return int(removed)
