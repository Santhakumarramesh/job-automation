"""
Phase 11 — Apply Queue Service
Central data model and state machine for the production-ready job approval queue.

Job states:
  skip | review_fit | review_resume | ready_for_approval |
  approved_for_apply | applying | applied | blocked

Package states:
  not_generated | generated | optimized_truth_safe | approved | uploaded
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "job_applications.db"

# ---------------------------------------------------------------------------
# State enums (as constants)
# ---------------------------------------------------------------------------

class JobQueueState:
    SKIP = "skip"
    REVIEW_FIT = "review_fit"
    REVIEW_RESUME = "review_resume"
    READY_FOR_APPROVAL = "ready_for_approval"
    APPROVED_FOR_APPLY = "approved_for_apply"
    APPLYING = "applying"
    APPLIED = "applied"
    BLOCKED = "blocked"

class PackageState:
    NOT_GENERATED = "not_generated"
    GENERATED = "generated"
    OPTIMIZED_TRUTH_SAFE = "optimized_truth_safe"
    APPROVED = "approved"
    UPLOADED = "uploaded"


# ---------------------------------------------------------------------------
# DB Setup
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS apply_queue (
    id TEXT PRIMARY KEY,
    job_url TEXT NOT NULL,
    job_title TEXT,
    company TEXT,
    job_description TEXT,
    
    -- Fit data
    role_family TEXT,
    seniority_band TEXT,
    role_match_score INTEGER DEFAULT 0,
    experience_match_score INTEGER DEFAULT 0,
    seniority_match_score INTEGER DEFAULT 0,
    overall_fit_score INTEGER DEFAULT 0,
    fit_decision TEXT,
    fit_reasons TEXT,               -- JSON array
    unsupported_requirements TEXT,  -- JSON array
    hard_blockers TEXT,             -- JSON array
    requirement_evidence_map TEXT,  -- JSON array
    
    -- ATS data
    ats_score INTEGER DEFAULT 0,
    truth_safe_ats_ceiling INTEGER DEFAULT 0,
    
    -- Package data
    resume_version_id TEXT,
    package_status TEXT DEFAULT 'not_generated',
    initial_ats_score INTEGER DEFAULT 0,
    final_ats_score INTEGER DEFAULT 0,
    covered_keywords TEXT,          -- JSON array
    truthful_missing_keywords TEXT, -- JSON array
    optimization_summary TEXT,
    resume_path TEXT,
    
    -- Queue state
    job_state TEXT DEFAULT 'review_fit',
    user_decision TEXT DEFAULT 'pending',   -- pending | approved | hold | skip
    safe_to_submit INTEGER DEFAULT 0,
    safe_to_autofill INTEGER DEFAULT 1,
    operator_approved INTEGER DEFAULT 0,
    blocker_fields TEXT,            -- JSON array
    review_fields TEXT,             -- JSON array
    
    -- Application result
    application_status TEXT,        -- applied | failed | skipped
    application_date TEXT,
    run_id TEXT,
    screenshots_path TEXT,
    error_message TEXT,
    
    -- Metadata
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    source TEXT DEFAULT 'linkedin',
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_queue_state ON apply_queue(job_state);
CREATE INDEX IF NOT EXISTS idx_queue_company ON apply_queue(company);
CREATE INDEX IF NOT EXISTS idx_queue_created ON apply_queue(created_at);
"""


@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        _ensure_schema(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for json_field in ["fit_reasons", "unsupported_requirements", "hard_blockers",
                       "requirement_evidence_map", "covered_keywords",
                       "truthful_missing_keywords", "blocker_fields", "review_fields"]:
        if d.get(json_field) and isinstance(d[json_field], str):
            try:
                d[json_field] = json.loads(d[json_field])
            except Exception:
                d[json_field] = []
    return d


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def upsert_queue_item(
    job_url: str,
    job_title: str,
    company: str,
    job_description: str = "",
    fit_data: Optional[dict] = None,
    ats_score: int = 0,
    truth_safe_ceiling: int = 0,
    source: str = "linkedin",
) -> str:
    """
    Insert or update a job in the apply queue.
    Returns the item ID.
    """
    fit = fit_data or {}

    # Determine initial state
    hard_blockers = fit.get("hard_blockers", [])
    fit_decision = fit.get("fit_decision", "review_fit")
    overall_score = fit.get("overall_fit_score", 0)

    if hard_blockers:
        state = JobQueueState.SKIP
    elif fit_decision == "apply" and overall_score >= 65:
        state = JobQueueState.READY_FOR_APPROVAL
    elif fit_decision in ("review_fit", "apply"):
        state = JobQueueState.REVIEW_FIT
    else:
        state = JobQueueState.SKIP

    with _db() as conn:
        # Check for existing item
        existing = conn.execute(
            "SELECT id FROM apply_queue WHERE job_url = ?", (job_url,)
        ).fetchone()

        if existing:
            item_id = existing["id"]
            conn.execute("""
                UPDATE apply_queue SET
                    job_title=?, company=?, job_description=?,
                    role_family=?, seniority_band=?,
                    role_match_score=?, experience_match_score=?, seniority_match_score=?,
                    overall_fit_score=?, fit_decision=?,
                    fit_reasons=?, unsupported_requirements=?, hard_blockers=?,
                    requirement_evidence_map=?,
                    ats_score=?, truth_safe_ats_ceiling=?,
                    job_state=?, source=?, updated_at=?
                WHERE id=?
            """, (
                job_title, company, job_description[:2000],
                fit.get("role_family", ""), fit.get("seniority_band", ""),
                fit.get("role_match_score", 0), fit.get("experience_match_score", 0),
                fit.get("seniority_match_score", 0), overall_score,
                fit_decision,
                json.dumps(fit.get("fit_reasons", [])),
                json.dumps(fit.get("unsupported_requirements", [])),
                json.dumps(fit.get("hard_blockers", [])),
                json.dumps(fit.get("requirement_evidence_map", [])[:10]),
                ats_score, truth_safe_ceiling,
                state, source, datetime.now().isoformat(),
                item_id,
            ))
        else:
            item_id = str(uuid.uuid4())
            conn.execute("""
                INSERT INTO apply_queue (
                    id, job_url, job_title, company, job_description,
                    role_family, seniority_band,
                    role_match_score, experience_match_score, seniority_match_score,
                    overall_fit_score, fit_decision,
                    fit_reasons, unsupported_requirements, hard_blockers,
                    requirement_evidence_map,
                    ats_score, truth_safe_ats_ceiling,
                    job_state, source
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                item_id, job_url, job_title, company, job_description[:2000],
                fit.get("role_family", ""), fit.get("seniority_band", ""),
                fit.get("role_match_score", 0), fit.get("experience_match_score", 0),
                fit.get("seniority_match_score", 0), overall_score,
                fit_decision,
                json.dumps(fit.get("fit_reasons", [])),
                json.dumps(fit.get("unsupported_requirements", [])),
                json.dumps(fit.get("hard_blockers", [])),
                json.dumps(fit.get("requirement_evidence_map", [])[:10]),
                ats_score, truth_safe_ceiling,
                state, source,
            ))
    return item_id


def attach_package(item_id: str, package: dict) -> None:
    """Attach a generated resume package to a queue item."""
    with _db() as conn:
        conn.execute("""
            UPDATE apply_queue SET
                resume_version_id=?, package_status=?,
                initial_ats_score=?, final_ats_score=?,
                truth_safe_ats_ceiling=?,
                covered_keywords=?, truthful_missing_keywords=?,
                optimization_summary=?, resume_path=?,
                updated_at=?
            WHERE id=?
        """, (
            package.get("resume_version_id", ""),
            package.get("package_status", PackageState.GENERATED),
            package.get("initial_ats_score", 0),
            package.get("final_ats_score", 0),
            package.get("truth_safe_ats_ceiling", 0),
            json.dumps(package.get("covered_keywords", [])),
            json.dumps(package.get("truthful_missing_keywords", [])),
            package.get("optimization_summary", ""),
            package.get("resume_path", ""),
            datetime.now().isoformat(),
            item_id,
        ))


def set_job_state(item_id: str, new_state: str, notes: str = "") -> None:
    """Transition a queue item to a new state."""
    with _db() as conn:
        conn.execute("""
            UPDATE apply_queue SET job_state=?, notes=?, updated_at=? WHERE id=?
        """, (new_state, notes, datetime.now().isoformat(), item_id))


def approve_job(item_id: str) -> None:
    """Approve a job for apply. Sets state → approved_for_apply."""
    with _db() as conn:
        conn.execute("""
            UPDATE apply_queue SET
                job_state=?, user_decision='approved', operator_approved=1,
                package_status=CASE WHEN package_status='optimized_truth_safe' THEN 'approved' ELSE package_status END,
                updated_at=?
            WHERE id=?
        """, (JobQueueState.APPROVED_FOR_APPLY, datetime.now().isoformat(), item_id))


def hold_job(item_id: str, notes: str = "") -> None:
    with _db() as conn:
        conn.execute("""
            UPDATE apply_queue SET user_decision='hold', notes=?, updated_at=? WHERE id=?
        """, (notes, datetime.now().isoformat(), item_id))


def skip_job(item_id: str, notes: str = "") -> None:
    with _db() as conn:
        conn.execute("""
            UPDATE apply_queue SET job_state=?, user_decision='skip', notes=?, updated_at=? WHERE id=?
        """, (JobQueueState.SKIP, notes, datetime.now().isoformat(), item_id))


def mark_applied(item_id: str, run_id: str = "", screenshots_path: str = "") -> None:
    with _db() as conn:
        conn.execute("""
            UPDATE apply_queue SET
                job_state=?, application_status='applied', application_date=?,
                run_id=?, screenshots_path=?, updated_at=?
            WHERE id=?
        """, (JobQueueState.APPLIED, datetime.now().isoformat(),
              run_id, screenshots_path, datetime.now().isoformat(), item_id))


def mark_blocked(item_id: str, error: str = "") -> None:
    with _db() as conn:
        conn.execute("""
            UPDATE apply_queue SET job_state=?, error_message=?, updated_at=? WHERE id=?
        """, (JobQueueState.BLOCKED, error[:500], datetime.now().isoformat(), item_id))


def get_queue(
    states: Optional[list[str]] = None,
    limit: int = 50,
) -> list[dict]:
    """Retrieve queue items, optionally filtered by state."""
    with _db() as conn:
        if states:
            placeholders = ",".join("?" * len(states))
            rows = conn.execute(
                f"SELECT * FROM apply_queue WHERE job_state IN ({placeholders}) ORDER BY overall_fit_score DESC LIMIT ?",
                states + [limit],
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM apply_queue ORDER BY overall_fit_score DESC LIMIT ?", (limit,)
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_approved_queue() -> list[dict]:
    """Return only approved, package-ready items ready for the runner."""
    return get_queue(states=[JobQueueState.APPROVED_FOR_APPLY])


def get_queue_summary() -> dict:
    """Return counts by state."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT job_state, COUNT(*) as cnt FROM apply_queue GROUP BY job_state"
        ).fetchall()
    return {r["job_state"]: r["cnt"] for r in rows}


def get_item_by_id(item_id: str) -> Optional[dict]:
    with _db() as conn:
        row = conn.execute("SELECT * FROM apply_queue WHERE id=?", (item_id,)).fetchone()
    return _row_to_dict(row) if row else None


def get_item_by_url(job_url: str) -> Optional[dict]:
    with _db() as conn:
        row = conn.execute("SELECT * FROM apply_queue WHERE job_url=?", (job_url,)).fetchone()
    return _row_to_dict(row) if row else None
