"""
Phase 8 — Resume Version Store
Persist immutable approved resume versions and metadata.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "job_applications.db"


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS resume_versions (
    resume_version_id TEXT PRIMARY KEY,
    approved_pdf_path TEXT,
    approved_filename TEXT,
    approved_hash TEXT,
    approved_at TEXT,
    approved_by TEXT,
    template_id TEXT,
    page_count INTEGER DEFAULT 0,
    layout_status TEXT,
    package_status TEXT,
    source TEXT DEFAULT 'package'
);
CREATE INDEX IF NOT EXISTS idx_resume_versions_approved_at ON resume_versions(approved_at);
"""


@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        conn.executescript(SCHEMA_SQL)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _hash_file(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    h = hashlib.sha256()
    with p.open("rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def create_resume_version(
    *,
    approved_pdf_path: str,
    approved_filename: str = "",
    approved_by: str = "user",
    template_id: str = "",
    page_count: int = 0,
    layout_status: str = "",
    package_status: str = "",
    source: str = "package",
    resume_version_id: Optional[str] = None,
) -> dict:
    rid = resume_version_id or f"rv_{uuid.uuid4().hex[:10]}"
    filename = approved_filename or Path(approved_pdf_path).name
    approved_hash = _hash_file(approved_pdf_path)
    approved_at = datetime.now().isoformat()

    with _db() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO resume_versions (
                resume_version_id, approved_pdf_path, approved_filename, approved_hash,
                approved_at, approved_by, template_id, page_count, layout_status,
                package_status, source
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                rid,
                approved_pdf_path,
                filename,
                approved_hash,
                approved_at,
                approved_by,
                template_id,
                int(page_count or 0),
                layout_status,
                package_status,
                source,
            ),
        )

    return {
        "resume_version_id": rid,
        "approved_pdf_path": approved_pdf_path,
        "approved_filename": filename,
        "approved_hash": approved_hash,
        "approved_at": approved_at,
        "approved_by": approved_by,
        "template_id": template_id,
        "page_count": int(page_count or 0),
        "layout_status": layout_status,
        "package_status": package_status,
        "source": source,
    }


def get_resume_version(resume_version_id: str) -> Optional[dict]:
    if not resume_version_id:
        return None
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM resume_versions WHERE resume_version_id=?",
            (resume_version_id,),
        ).fetchone()
    return dict(row) if row else None


def list_resume_versions(limit: int = 50) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM resume_versions ORDER BY approved_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
