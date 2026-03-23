"""
Database-backed application tracker. SQLite by default; Postgres via DATABASE_URL.
Replaces CSV for production use. Backward compatible: migrates from CSV on first run.
"""

import json
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
DEFAULT_DB_PATH = _PROJECT_ROOT / "job_applications.db"
CSV_FILE = _PROJECT_ROOT / "job_applications.csv"

TRACKER_COLUMNS = [
    "id", "source", "job_id", "job_url", "apply_url", "company", "position",
    "status", "submission_status", "easy_apply_confirmed", "apply_mode",
    "fit_decision", "ats_score", "resume_path", "cover_letter_path",
    "job_description", "applied_at", "recruiter_response", "screenshots_path",
    "qa_audit", "retry_state",
]


def _get_db_path() -> Path:
    """Resolve DB path from env or default."""
    url = os.getenv("DATABASE_URL", "")
    if url and url.startswith("sqlite"):
        # sqlite:///path/to/db
        return Path(url.replace("sqlite:///", ""))
    return Path(os.getenv("TRACKER_DB_PATH", str(DEFAULT_DB_PATH)))


def _get_connection():
    """Get SQLite connection."""
    path = _get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(path))


def _init_schema(conn: sqlite3.Connection):
    """Create applications table if not exists."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id TEXT PRIMARY KEY,
            source TEXT,
            job_id TEXT,
            job_url TEXT,
            apply_url TEXT,
            company TEXT,
            position TEXT,
            status TEXT,
            submission_status TEXT,
            easy_apply_confirmed TEXT,
            apply_mode TEXT,
            fit_decision TEXT,
            ats_score TEXT,
            resume_path TEXT,
            cover_letter_path TEXT,
            job_description TEXT,
            applied_at TEXT,
            recruiter_response TEXT,
            screenshots_path TEXT,
            qa_audit TEXT,
            retry_state TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def migrate_from_csv(conn: sqlite3.Connection) -> int:
    """Import existing CSV rows into DB. Returns count migrated."""
    if not CSV_FILE.exists():
        return 0
    try:
        df = pd.read_csv(CSV_FILE)
    except Exception:
        return 0
    if df.empty:
        return 0
    # Map legacy columns
    legacy = {"Date Applied": "applied_at", "Company": "company", "Position": "position",
              "Status": "status", "Resume Path": "resume_path", "Cover Letter Path": "cover_letter_path",
              "Job Description": "job_description"}
    for old, new in legacy.items():
        if old in df.columns and new not in df.columns:
            df[new] = df[old]
    cols = [c for c in TRACKER_COLUMNS if c in df.columns]
    cursor = conn.cursor()
    count = 0
    for _, row in df.iterrows():
        rid = str(row.get("id", uuid.uuid4())) if pd.notna(row.get("id")) else str(uuid.uuid4())
        vals = [str(row.get(c, "") or "")[:500] if c != "job_description" else str(row.get(c, "") or "")[:2000] for c in TRACKER_COLUMNS]
        vals[0] = rid
        try:
            cursor.execute(
                f"INSERT OR IGNORE INTO applications ({', '.join(TRACKER_COLUMNS)}) VALUES ({', '.join('?'*len(TRACKER_COLUMNS))})",
                vals,
            )
            if cursor.rowcount:
                count += 1
        except Exception:
            pass
    conn.commit()
    return count


def initialize_tracker_db():
    """Create DB and schema; migrate from CSV if needed."""
    conn = _get_connection()
    try:
        _init_schema(conn)
        migrated = migrate_from_csv(conn)
        if migrated:
            print(f"✅ Migrated {migrated} applications from CSV to DB.")
    finally:
        conn.close()


def log_application_db(row: dict) -> str:
    """Log one application. Returns id."""
    row.setdefault("id", str(uuid.uuid4()))
    row.setdefault("applied_at", datetime.now().isoformat())
    conn = _get_connection()
    try:
        _init_schema(conn)
        cols = [c for c in TRACKER_COLUMNS if c in row]
        vals = [str(row.get(c, "") or "")[:500] if c != "job_description" else str(row.get(c, "") or "")[:2000] for c in cols]
        conn.execute(
            f"INSERT INTO applications ({', '.join(cols)}) VALUES ({', '.join('?'*len(cols))})",
            vals,
        )
        conn.commit()
        return row["id"]
    finally:
        conn.close()


def load_applications_db() -> pd.DataFrame:
    """Load all applications as DataFrame."""
    conn = _get_connection()
    try:
        _init_schema(conn)
        df = pd.read_sql_query("SELECT * FROM applications ORDER BY applied_at DESC", conn)
        return df.reindex(columns=TRACKER_COLUMNS, fill_value="")
    except Exception:
        return pd.DataFrame(columns=TRACKER_COLUMNS)
    finally:
        conn.close()


def save_applications_db(df: pd.DataFrame):
    """Replace all applications with DataFrame contents (for editor saves)."""
    conn = _get_connection()
    try:
        _init_schema(conn)
        conn.execute("DELETE FROM applications")
        cols = [c for c in TRACKER_COLUMNS if c in df.columns]
        for _, row in df.iterrows():
            vals = [str(row.get(c, "") or "")[:500] if c != "job_description" else str(row.get(c, "") or "")[:2000] for c in cols]
            conn.execute(f"INSERT INTO applications ({', '.join(cols)}) VALUES ({', '.join('?'*len(cols))})", vals)
        conn.commit()
    finally:
        conn.close()
