"""
Phase 6 — Apply Queue Service
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

from services.queue_transitions import (
    determine_initial_state,
    determine_state_after_package,
    recommended_action,
)

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


def _audit_queue_event(action: str, item_id: str, *, extra: Optional[dict] = None, status: str = "") -> None:
    """Emit lifecycle audit events for queue transitions."""
    try:
        from services.observability import audit_log

        item = get_item_by_id(item_id)
        if not item:
            return
        payload = {
            "job_url": item.get("job_url", ""),
            "queue_state": item.get("job_state", ""),
            "package_state": item.get("package_status", ""),
            "approval_state": item.get("approval_status", ""),
            "runner_state": item.get("runner_state", ""),
            "application_status": item.get("application_status", ""),
        }
        if extra:
            payload.update(extra)
        audit_log(
            action,
            job_id=item_id,
            company=item.get("company", ""),
            position=item.get("job_title", ""),
            status=status or item.get("job_state", ""),
            extra=payload,
        )
    except Exception:
        pass


def queue_row_summary(item: dict) -> dict:
    """
    Minimal queue row used by UI/exports.
    """
    return {
        "company": item.get("company", ""),
        "job_title": item.get("job_title", ""),
        "job_url": item.get("job_url", ""),
        "role_family": item.get("role_family", ""),
        "overall_fit_score": item.get("overall_fit_score", 0),
        "ats_score": item.get("ats_score", 0),
        "truth_safe_ats_ceiling": item.get("truth_safe_ats_ceiling", 0),
        "package_status": item.get("package_status", ""),
        "approved_resume_version_id": item.get("approved_resume_version_id", ""),
        "approved_resume_path": item.get("approved_resume_path", ""),
        "unsupported_requirements_count": item.get("unsupported_requirements_count", 0),
        "recommended_action": item.get("recommended_action", "review_fit"),
    }


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

    -- Approval metadata
    approval_status TEXT DEFAULT 'pending', -- pending | approved | hold | rejected
    approval_metadata TEXT,                 -- JSON object
    approved_resume_version_id TEXT,
    approved_resume_path TEXT,
    approved_at TEXT,
    approved_by TEXT,

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

    -- Runner state (Phase 10)
    runner_state TEXT DEFAULT 'queued',
    runner_error TEXT,
    runner_attempts INTEGER DEFAULT 0,
    runner_last_started TEXT,
    runner_last_finished TEXT,
    
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
    existing = {row[1] for row in conn.execute("PRAGMA table_info(apply_queue)").fetchall()}
    additions = {
        "job_title": "TEXT",
        "company": "TEXT",
        "job_description": "TEXT",
        "role_family": "TEXT",
        "seniority_band": "TEXT",
        "role_match_score": "INTEGER DEFAULT 0",
        "experience_match_score": "INTEGER DEFAULT 0",
        "seniority_match_score": "INTEGER DEFAULT 0",
        "overall_fit_score": "INTEGER DEFAULT 0",
        "fit_decision": "TEXT",
        "fit_reasons": "TEXT",
        "unsupported_requirements": "TEXT",
        "hard_blockers": "TEXT",
        "requirement_evidence_map": "TEXT",
        "ats_score": "INTEGER DEFAULT 0",
        "truth_safe_ats_ceiling": "INTEGER DEFAULT 0",
        "resume_version_id": "TEXT",
        "package_status": "TEXT DEFAULT 'not_generated'",
        "initial_ats_score": "INTEGER DEFAULT 0",
        "final_ats_score": "INTEGER DEFAULT 0",
        "covered_keywords": "TEXT",
        "truthful_missing_keywords": "TEXT",
        "optimization_summary": "TEXT",
        "resume_path": "TEXT",
        "approval_status": "TEXT DEFAULT 'pending'",
        "approval_metadata": "TEXT",
        "approved_resume_version_id": "TEXT",
        "approved_resume_path": "TEXT",
        "approved_at": "TEXT",
        "approved_by": "TEXT",
        "job_state": "TEXT DEFAULT 'review_fit'",
        "user_decision": "TEXT DEFAULT 'pending'",
        "safe_to_submit": "INTEGER DEFAULT 0",
        "safe_to_autofill": "INTEGER DEFAULT 1",
        "operator_approved": "INTEGER DEFAULT 0",
        "blocker_fields": "TEXT",
        "review_fields": "TEXT",
        "application_status": "TEXT",
        "application_date": "TEXT",
        "run_id": "TEXT",
        "screenshots_path": "TEXT",
        "error_message": "TEXT",
        "runner_state": "TEXT DEFAULT 'queued'",
        "runner_error": "TEXT",
        "runner_attempts": "INTEGER DEFAULT 0",
        "runner_last_started": "TEXT",
        "runner_last_finished": "TEXT",
        "created_at": "TEXT",
        "updated_at": "TEXT",
        "source": "TEXT DEFAULT 'linkedin'",
        "notes": "TEXT",
    }
    for col, ddl in additions.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE apply_queue ADD COLUMN {col} {ddl}")


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for json_field in ["fit_reasons", "unsupported_requirements", "hard_blockers",
                       "requirement_evidence_map", "covered_keywords",
                       "truthful_missing_keywords", "blocker_fields", "review_fields",
                       "approval_metadata"]:
        if d.get(json_field) and isinstance(d[json_field], str):
            try:
                d[json_field] = json.loads(d[json_field])
            except Exception:
                d[json_field] = []
    d["unsupported_requirements_count"] = len(d.get("unsupported_requirements") or [])
    d["recommended_action"] = recommended_action(
        job_state=d.get("job_state", ""),
        package_status=d.get("package_status", ""),
    )
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

    state = determine_initial_state(
        fit_decision=fit_decision,
        overall_fit_score=int(overall_score or 0),
        hard_blockers=hard_blockers,
    )

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
        row = conn.execute(
            "SELECT job_state, fit_decision, overall_fit_score, hard_blockers, unsupported_requirements FROM apply_queue WHERE id=?",
            (item_id,),
        ).fetchone()
        current_state = row["job_state"] if row else JobQueueState.REVIEW_FIT
        fit_decision = row["fit_decision"] if row else ""
        overall_fit_score = int(row["overall_fit_score"] or 0) if row else 0
        try:
            hard_blockers = json.loads(row["hard_blockers"]) if row and row["hard_blockers"] else []
        except Exception:
            hard_blockers = []
        try:
            unsupported = json.loads(row["unsupported_requirements"]) if row and row["unsupported_requirements"] else []
        except Exception:
            unsupported = []

        next_state = determine_state_after_package(
            current_state=current_state,
            fit_decision=fit_decision,
            overall_fit_score=overall_fit_score,
            package_status=package.get("package_status", PackageState.GENERATED),
            hard_blockers=hard_blockers,
            unsupported_requirements=unsupported,
        )
        conn.execute("""
            UPDATE apply_queue SET
                resume_version_id=?, package_status=?,
                initial_ats_score=?, final_ats_score=?,
                truth_safe_ats_ceiling=?,
                covered_keywords=?, truthful_missing_keywords=?,
                optimization_summary=?, resume_path=?,
                job_state=?,
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
            next_state,
            datetime.now().isoformat(),
            item_id,
        ))
    _audit_queue_event(
        "package_generated",
        item_id,
        extra={
            "resume_version_id": package.get("resume_version_id", ""),
            "package_status": package.get("package_status", PackageState.GENERATED),
            "initial_ats_score": package.get("initial_ats_score", 0),
            "final_ats_score": package.get("final_ats_score", 0),
            "truth_safe_ats_ceiling": package.get("truth_safe_ats_ceiling", 0),
        },
        status=next_state,
    )


def set_job_state(item_id: str, new_state: str, notes: str = "") -> None:
    """Transition a queue item to a new state."""
    with _db() as conn:
        conn.execute("""
            UPDATE apply_queue SET job_state=?, notes=?, updated_at=? WHERE id=?
        """, (new_state, notes, datetime.now().isoformat(), item_id))


def approve_job(item_id: str, approval_metadata: Optional[dict] = None) -> None:
    """Approve a job for apply. Sets state → approved_for_apply."""
    approval_metadata = approval_metadata or {}
    with _db() as conn:
        conn.execute("""
            UPDATE apply_queue SET
                job_state=?, user_decision='approved', operator_approved=1,
                package_status=CASE WHEN package_status='optimized_truth_safe' THEN 'approved' ELSE package_status END,
                approval_status='approved',
                approval_metadata=?,
                approved_resume_version_id=?,
                approved_resume_path=?,
                approved_at=?,
                approved_by=?,
                updated_at=?
            WHERE id=?
        """, (
            JobQueueState.APPROVED_FOR_APPLY,
            json.dumps(approval_metadata),
            approval_metadata.get("approved_resume_version_id", ""),
            approval_metadata.get("approved_resume_path", ""),
            approval_metadata.get("approved_at", datetime.now().isoformat()),
            approval_metadata.get("approved_by", "user"),
            datetime.now().isoformat(),
            item_id,
        ))
    _audit_queue_event(
        "package_approved",
        item_id,
        extra={
            "approved_by": approval_metadata.get("approved_by", "user"),
            "approved_at": approval_metadata.get("approved_at", ""),
            "approved_resume_version_id": approval_metadata.get("approved_resume_version_id", ""),
            "approved_resume_path": approval_metadata.get("approved_resume_path", ""),
        },
        status=JobQueueState.APPROVED_FOR_APPLY,
    )


def hold_job(item_id: str, notes: str = "") -> None:
    with _db() as conn:
        conn.execute("""
            UPDATE apply_queue SET
                job_state=?, user_decision='hold',
                approval_status='hold',
                notes=?, updated_at=?
            WHERE id=?
        """, (JobQueueState.REVIEW_FIT, notes, datetime.now().isoformat(), item_id))


def reject_job(item_id: str, notes: str = "") -> None:
    """Reject a job; mark as skipped with reject decision."""
    with _db() as conn:
        conn.execute("""
            UPDATE apply_queue SET
                job_state=?, user_decision='rejected',
                approval_status='rejected',
                notes=?, updated_at=?
            WHERE id=?
        """, (JobQueueState.SKIP, notes, datetime.now().isoformat(), item_id))


def send_back_for_resume_review(item_id: str, notes: str = "") -> None:
    """Send back to resume review; clears existing package so it can be regenerated."""
    with _db() as conn:
        conn.execute("""
            UPDATE apply_queue SET
                job_state=?,
                package_status=?,
                resume_version_id='',
                resume_path='',
                user_decision='pending',
                notes=?, updated_at=?
            WHERE id=?
        """, (JobQueueState.REVIEW_RESUME, PackageState.NOT_GENERATED, notes, datetime.now().isoformat(), item_id))


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
    _audit_queue_event(
        "application_submitted",
        item_id,
        extra={"run_id": run_id, "screenshots_path": screenshots_path},
        status=JobQueueState.APPLIED,
    )


def mark_blocked(item_id: str, error: str = "") -> None:
    with _db() as conn:
        conn.execute("""
            UPDATE apply_queue SET job_state=?, error_message=?, updated_at=? WHERE id=?
        """, (JobQueueState.BLOCKED, error[:500], datetime.now().isoformat(), item_id))


def mark_runner_started(item_id: str) -> None:
    with _db() as conn:
        conn.execute(
            """
            UPDATE apply_queue SET
                runner_state='running',
                runner_attempts=COALESCE(runner_attempts, 0) + 1,
                runner_last_started=?,
                updated_at=?
            WHERE id=?
            """,
            (datetime.now().isoformat(), datetime.now().isoformat(), item_id),
        )
    _audit_queue_event("runner_started", item_id, status=JobQueueState.APPLYING)


def set_runner_state(item_id: str, state: str, error: str = "") -> None:
    with _db() as conn:
        conn.execute(
            """
            UPDATE apply_queue SET
                runner_state=?,
                runner_error=?,
                runner_last_finished=?,
                updated_at=?
            WHERE id=?
            """,
            (state, error[:500], datetime.now().isoformat(), datetime.now().isoformat(), item_id),
        )
    if state == "stopped_review_required":
        _audit_queue_event(
            "runner_stopped_review_required",
            item_id,
            extra={"runner_state": state, "error": error[:200]},
        )


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
