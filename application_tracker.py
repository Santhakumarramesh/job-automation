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

import pandas as pd

# Use project root so path works from any cwd
_SCRIPT_DIR = Path(__file__).resolve().parent
APPLICATION_FILE = _SCRIPT_DIR / "job_applications.csv"

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
    "fit_decision",
    "ats_score",
    "resume_path",
    "cover_letter_path",
    "job_description",
    "applied_at",
    "recruiter_response",  # Pending, positive, negative
    "screenshots_path",    # JSON list
    "qa_audit",           # JSON
    "retry_state",        # For failed
]

# Legacy columns for backward compat
LEGACY_COLUMNS = ["Date Applied", "Company", "Position", "Status", "Resume Path", "Cover Letter Path", "Job Description"]


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
        "fit_decision": state.get("fit_decision", ""),
        "ats_score": state.get("final_ats_score", state.get("initial_ats_score", "")),
        "resume_path": state.get("final_pdf_path", ""),
        "cover_letter_path": state.get("cover_letter_pdf_path", ""),
        "job_description": state.get("job_description", ""),
        "applied_at": datetime.now().isoformat(),
        "recruiter_response": "Pending",
        "screenshots_path": "",
        "qa_audit": "",
        "retry_state": "",
    }
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


def log_application_from_result(run_result, resume_path: str = "", cover_path: str = "", job_metadata: dict = None):
    """
    Log from ApplicationRunner RunResult. Used by apply_linkedin_jobs.py.
    job_metadata: optional dict with fit_decision, ats_score, apply_mode, easy_apply_confirmed, unsupported_requirements.
    """
    initialize_tracker()
    job_metadata = job_metadata or {}
    screenshots_json = json.dumps(run_result.screenshot_paths) if run_result.screenshot_paths else ""
    qa_json = json.dumps(run_result.qa_audit) if run_result.qa_audit else ""
    status_map = {
        "applied": "Applied",
        "manual_assist_ready": "Manual Assist Ready",
        "skipped": "Skipped – Low Fit",
        "dry_run": "Dry Run Complete",
        "failed": "Failed – Form Unmapped",
    }

    row = {
        "id": str(uuid.uuid4()),
        "source": "linkedin_mcp",
        "job_id": job_metadata.get("job_id", ""),
        "job_url": run_result.job_url,
        "apply_url": run_result.job_url,
        "company": run_result.company,
        "position": run_result.position,
        "status": "Applied" if run_result.status == "applied" else ("Interviewing" if run_result.status == "manual_assist_ready" else "Rejected"),
        "submission_status": status_map.get(run_result.status, run_result.status),
        "easy_apply_confirmed": job_metadata.get("easy_apply_confirmed", ""),
        "apply_mode": job_metadata.get("apply_mode", ""),
        "fit_decision": job_metadata.get("fit_decision", ""),
        "ats_score": job_metadata.get("ats_score", job_metadata.get("final_ats_score", "")),
        "resume_path": resume_path,
        "cover_letter_path": cover_path,
        "job_description": job_metadata.get("description", ""),
        "applied_at": run_result.applied_at or datetime.now().isoformat(),
        "recruiter_response": "Pending",
        "screenshots_path": screenshots_json,
        "qa_audit": qa_json,
        "retry_state": "",
    }
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


def load_applications() -> pd.DataFrame:
    """Load all logged applications. Handles legacy and rich schema."""
    initialize_tracker()
    if USE_DB:
        try:
            from services.tracker_db import load_applications_db
            return load_applications_db()
        except ImportError:
            pass
    try:
        df = pd.read_csv(APPLICATION_FILE)
        df = _ensure_columns(df)
        return df
    except (pd.errors.EmptyDataError, Exception):
        return pd.DataFrame(columns=TRACKER_COLUMNS)
