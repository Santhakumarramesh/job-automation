"""
Database-backed application tracker.
- SQLite: default file `job_applications.db` or `sqlite:///path` via DATABASE_URL / TRACKER_DB_PATH.
- Postgres: `TRACKER_DATABASE_URL` or `DATABASE_URL` when it starts with postgresql:// (requires TRACKER_USE_DB=1).

Install Postgres driver: pip install .[postgres]  (psycopg2-binary)
Postgres DDL revisions: Alembic in alembic/ — pip install .[migrations]; see docs/MIGRATIONS.md
"""

import atexit
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Generator, Optional

import pandas as pd

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
DEFAULT_DB_PATH = _PROJECT_ROOT / "job_applications.db"
CSV_FILE = _PROJECT_ROOT / "job_applications.csv"

TRACKER_COLUMNS = [
    "id", "source", "job_id", "job_url", "apply_url", "company", "position",
    "status", "submission_status", "easy_apply_confirmed", "apply_mode", "policy_reason",
    "fit_decision", "ats_score", "resume_path", "cover_letter_path",
    "job_description", "applied_at", "recruiter_response", "screenshots_path",
    "qa_audit", "artifacts_manifest", "retry_state", "user_id",
    "follow_up_at", "follow_up_status", "follow_up_note",
    "interview_stage", "offer_outcome",
]

FOLLOW_UP_COLUMN_SET = frozenset({"follow_up_at", "follow_up_status", "follow_up_note"})
PIPELINE_COLUMN_SET = frozenset({"interview_stage", "offer_outcome"})

_PG_PLACEHOLDER = "%s"
_SQLITE_PLACEHOLDER = "?"


def _tracker_database_url() -> str:
    """URL for tracker DB: TRACKER_DATABASE_URL wins, else DATABASE_URL."""
    return (os.getenv("TRACKER_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()


def _use_postgres() -> bool:
    if os.getenv("TRACKER_USE_DB", "").lower() not in ("1", "true", "yes"):
        return False
    u = _tracker_database_url()
    return u.startswith(("postgresql://", "postgres://"))


def _get_db_path() -> Path:
    """Resolve SQLite DB path from env or default."""
    url = os.getenv("DATABASE_URL", "")
    if url and url.startswith("sqlite"):
        return Path(url.replace("sqlite:///", ""))
    return Path(os.getenv("TRACKER_DB_PATH", str(DEFAULT_DB_PATH)))


_pg_pool: Optional[Any] = None


def _pg_pool_enabled() -> bool:
    return os.getenv("TRACKER_PG_POOL", "1").lower() not in ("0", "false", "no")


def close_tracker_pg_pool() -> None:
    """Close Postgres pool (tests, worker shutdown, URL change)."""
    global _pg_pool
    if _pg_pool is not None:
        try:
            _pg_pool.closeall()
        except Exception:
            pass
        _pg_pool = None


def _get_pg_pool():
    """Thread-safe pool for FastAPI sync routes and workers."""
    global _pg_pool
    if _pg_pool is None:
        from psycopg2 import pool

        dsn = _tracker_database_url()
        minc = max(1, int(os.getenv("TRACKER_PG_POOL_MIN", "1")))
        maxc = max(minc, int(os.getenv("TRACKER_PG_POOL_MAX", "10")))
        _pg_pool = pool.ThreadedConnectionPool(minc, maxc, dsn)
    return _pg_pool


atexit.register(close_tracker_pg_pool)


@contextmanager
def _pg_connection() -> Generator[Any, None, None]:
    if not _pg_pool_enabled():
        import psycopg2
        conn = psycopg2.connect(_tracker_database_url())
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return

    p = _get_pg_pool()
    conn = p.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        p.putconn(conn)


@contextmanager
def _sqlite_connection() -> Generator[sqlite3.Connection, None, None]:
    path = _get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _pg_table_columns(conn) -> set:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'applications'
        """
    )
    return {r[0] for r in cur.fetchall()}


def _pg_ensure_column(conn, name: str, ddl: str) -> None:
    if name not in _pg_table_columns(conn):
        cur = conn.cursor()
        cur.execute(f"ALTER TABLE applications ADD COLUMN {name} {ddl}")
        conn.commit()


def _init_schema_sqlite(conn: sqlite3.Connection) -> None:
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
            policy_reason TEXT DEFAULT '',
            fit_decision TEXT,
            ats_score TEXT,
            resume_path TEXT,
            cover_letter_path TEXT,
            job_description TEXT,
            applied_at TEXT,
            recruiter_response TEXT,
            screenshots_path TEXT,
            qa_audit TEXT,
            artifacts_manifest TEXT DEFAULT '{}',
            retry_state TEXT,
            user_id TEXT DEFAULT '',
            follow_up_at TEXT DEFAULT '',
            follow_up_status TEXT DEFAULT '',
            follow_up_note TEXT DEFAULT '',
            interview_stage TEXT DEFAULT '',
            offer_outcome TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    _migrate_sqlite_columns(conn)


def _migrate_sqlite_columns(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(applications)")
    cols = {row[1] for row in cur.fetchall()}
    if "user_id" not in cols:
        conn.execute("ALTER TABLE applications ADD COLUMN user_id TEXT DEFAULT ''")
        conn.commit()
    if "policy_reason" not in cols:
        conn.execute("ALTER TABLE applications ADD COLUMN policy_reason TEXT DEFAULT ''")
        conn.commit()
    if "artifacts_manifest" not in cols:
        conn.execute("ALTER TABLE applications ADD COLUMN artifacts_manifest TEXT DEFAULT '{}'")
        conn.commit()
    if "follow_up_at" not in cols:
        conn.execute("ALTER TABLE applications ADD COLUMN follow_up_at TEXT DEFAULT ''")
        conn.commit()
    if "follow_up_status" not in cols:
        conn.execute("ALTER TABLE applications ADD COLUMN follow_up_status TEXT DEFAULT ''")
        conn.commit()
    if "follow_up_note" not in cols:
        conn.execute("ALTER TABLE applications ADD COLUMN follow_up_note TEXT DEFAULT ''")
        conn.commit()
    if "interview_stage" not in cols:
        conn.execute("ALTER TABLE applications ADD COLUMN interview_stage TEXT DEFAULT ''")
        conn.commit()
    if "offer_outcome" not in cols:
        conn.execute("ALTER TABLE applications ADD COLUMN offer_outcome TEXT DEFAULT ''")
        conn.commit()


def _init_schema_postgres(conn) -> None:
    cur = conn.cursor()
    cur.execute("""
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
            policy_reason TEXT DEFAULT '',
            fit_decision TEXT,
            ats_score TEXT,
            resume_path TEXT,
            cover_letter_path TEXT,
            job_description TEXT,
            applied_at TEXT,
            recruiter_response TEXT,
            screenshots_path TEXT,
            qa_audit TEXT,
            artifacts_manifest TEXT DEFAULT '{}',
            retry_state TEXT,
            user_id TEXT DEFAULT '',
            follow_up_at TEXT DEFAULT '',
            follow_up_status TEXT DEFAULT '',
            follow_up_note TEXT DEFAULT '',
            interview_stage TEXT DEFAULT '',
            offer_outcome TEXT DEFAULT '',
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    conn.commit()
    _pg_ensure_column(conn, "user_id", "TEXT DEFAULT ''")
    _pg_ensure_column(conn, "policy_reason", "TEXT DEFAULT ''")
    _pg_ensure_column(conn, "artifacts_manifest", "TEXT DEFAULT '{}'")
    _pg_ensure_column(conn, "follow_up_at", "TEXT DEFAULT ''")
    _pg_ensure_column(conn, "follow_up_status", "TEXT DEFAULT ''")
    _pg_ensure_column(conn, "follow_up_note", "TEXT DEFAULT ''")
    _pg_ensure_column(conn, "interview_stage", "TEXT DEFAULT ''")
    _pg_ensure_column(conn, "offer_outcome", "TEXT DEFAULT ''")


def migrate_from_csv_sqlite(conn: sqlite3.Connection) -> int:
    if not CSV_FILE.exists():
        return 0
    try:
        df = pd.read_csv(CSV_FILE)
    except Exception:
        return 0
    if df.empty:
        return 0
    legacy = {"Date Applied": "applied_at", "Company": "company", "Position": "position",
              "Status": "status", "Resume Path": "resume_path", "Cover Letter Path": "cover_letter_path",
              "Job Description": "job_description"}
    for old, new in legacy.items():
        if old in df.columns and new not in df.columns:
            df[new] = df[old]
    cursor = conn.cursor()
    count = 0
    for _, row in df.iterrows():
        rid = str(row.get("id", uuid.uuid4())) if pd.notna(row.get("id")) else str(uuid.uuid4())
        vals = [_row_vals(row, c) for c in TRACKER_COLUMNS]
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


def migrate_from_csv_postgres(conn) -> int:
    if not CSV_FILE.exists():
        return 0
    try:
        df = pd.read_csv(CSV_FILE)
    except Exception:
        return 0
    if df.empty:
        return 0
    legacy = {"Date Applied": "applied_at", "Company": "company", "Position": "position",
              "Status": "status", "Resume Path": "resume_path", "Cover Letter Path": "cover_letter_path",
              "Job Description": "job_description"}
    for old, new in legacy.items():
        if old in df.columns and new not in df.columns:
            df[new] = df[old]
    cur = conn.cursor()
    count = 0
    ph = ", ".join([_PG_PLACEHOLDER] * len(TRACKER_COLUMNS))
    sql = (
        f"INSERT INTO applications ({', '.join(TRACKER_COLUMNS)}) VALUES ({ph}) "
        "ON CONFLICT (id) DO NOTHING"
    )
    for _, row in df.iterrows():
        rid = str(row.get("id", uuid.uuid4())) if pd.notna(row.get("id")) else str(uuid.uuid4())
        vals = [_row_vals(row, c) for c in TRACKER_COLUMNS]
        vals[0] = rid
        try:
            cur.execute(sql, vals)
            if cur.rowcount:
                count += 1
        except Exception:
            pass
    conn.commit()
    return count


def _row_vals(row, col: str) -> str:
    v = row.get(col, "")
    if col == "job_description":
        return str(v or "")[:2000]
    if col == "artifacts_manifest":
        return str(v or "")[:8000] if v not in (None, "") else "{}"
    if col == "follow_up_note":
        return str(v or "")[:2000]
    if col in ("interview_stage", "offer_outcome"):
        return str(v or "").strip()[:120]
    return str(v or "")[:500]


def initialize_tracker_db():
    """Create DB and schema; migrate from CSV if needed."""
    if _use_postgres():
        with _pg_connection() as conn:
            _init_schema_postgres(conn)
            migrated = migrate_from_csv_postgres(conn)
            if migrated:
                print(f"✅ Migrated {migrated} applications from CSV to Postgres.")
        return
    with _sqlite_connection() as conn:
        _init_schema_sqlite(conn)
        migrated = migrate_from_csv_sqlite(conn)
        if migrated:
            print(f"✅ Migrated {migrated} applications from CSV to SQLite.")


def log_application_db(row: dict) -> str:
    """Log one application. Returns id."""
    row.setdefault("id", str(uuid.uuid4()))
    row.setdefault("applied_at", datetime.now().isoformat())
    row.setdefault("user_id", "")
    row.setdefault("policy_reason", "")
    row.setdefault("artifacts_manifest", "{}")
    cols = [c for c in TRACKER_COLUMNS if c in row]
    vals = [_cell(row, c) for c in cols]

    if _use_postgres():
        with _pg_connection() as conn:
            _init_schema_postgres(conn)
            ph = ", ".join([_PG_PLACEHOLDER] * len(cols))
            cur = conn.cursor()
            cur.execute(
                f"INSERT INTO applications ({', '.join(cols)}) VALUES ({ph})",
                vals,
            )
        return row["id"]

    with _sqlite_connection() as conn:
        _init_schema_sqlite(conn)
        cur = conn.cursor()
        cur.execute(
            f"INSERT INTO applications ({', '.join(cols)}) VALUES ({', '.join('?'*len(cols))})",
            vals,
        )
    return row["id"]


def _cell(row: dict, c: str) -> str:
    v = row.get(c, "")
    if c == "job_description":
        return str(v or "")[:2000]
    if c == "artifacts_manifest":
        return str(v or "")[:8000] if v not in (None, "") else "{}"
    if c == "follow_up_note":
        return str(v or "")[:2000]
    if c in ("interview_stage", "offer_outcome"):
        return str(v or "").strip()[:120]
    return str(v or "")[:500]


def update_application_follow_up_partial(
    row_id: str,
    scope_user_id: Optional[str],
    updates: dict,
) -> bool:
    """
    PATCH follow-up fields on one application row.
    scope_user_id None = match id only (demo / admin-style); else require user_id match.
    """
    rid = str(row_id or "").strip()
    if not rid:
        return False
    patch = {k: v for k, v in updates.items() if k in FOLLOW_UP_COLUMN_SET}
    if not patch:
        return False
    for k, v in list(patch.items()):
        if v is None:
            patch[k] = ""
        elif isinstance(v, str):
            patch[k] = v.strip()

    if _use_postgres():
        with _pg_connection() as conn:
            _init_schema_postgres(conn)
            set_parts = [f"{k} = {_PG_PLACEHOLDER}" for k in patch]
            vals = [_cell(patch, k) for k in patch]
            if scope_user_id is None:
                sql = f"UPDATE applications SET {', '.join(set_parts)} WHERE id = {_PG_PLACEHOLDER}"
                vals.append(rid)
            else:
                sql = (
                    f"UPDATE applications SET {', '.join(set_parts)} "
                    f"WHERE id = {_PG_PLACEHOLDER} AND user_id = {_PG_PLACEHOLDER}"
                )
                vals.extend([rid, str(scope_user_id)])
            cur = conn.cursor()
            cur.execute(sql, vals)
            return cur.rowcount > 0

    with _sqlite_connection() as conn:
        _init_schema_sqlite(conn)
        set_parts = [f"{k} = ?" for k in patch]
        vals = [_cell(patch, k) for k in patch]
        if scope_user_id is None:
            sql = f"UPDATE applications SET {', '.join(set_parts)} WHERE id = ?"
            vals.append(rid)
        else:
            sql = (
                f"UPDATE applications SET {', '.join(set_parts)} "
                "WHERE id = ? AND user_id = ?"
            )
            vals.extend([rid, str(scope_user_id)])
        cur = conn.cursor()
        cur.execute(sql, vals)
        return cur.rowcount > 0


def update_application_pipeline_partial(
    row_id: str,
    scope_user_id: Optional[str],
    updates: dict,
) -> bool:
    rid = str(row_id or "").strip()
    if not rid:
        return False
    patch = {k: v for k, v in updates.items() if k in PIPELINE_COLUMN_SET}
    if not patch:
        return False
    for k, v in list(patch.items()):
        if v is None:
            patch[k] = ""
        elif isinstance(v, str):
            patch[k] = v.strip()

    if _use_postgres():
        with _pg_connection() as conn:
            _init_schema_postgres(conn)
            set_parts = [f"{k} = {_PG_PLACEHOLDER}" for k in patch]
            vals = [_cell(patch, k) for k in patch]
            if scope_user_id is None:
                sql = f"UPDATE applications SET {', '.join(set_parts)} WHERE id = {_PG_PLACEHOLDER}"
                vals.append(rid)
            else:
                sql = (
                    f"UPDATE applications SET {', '.join(set_parts)} "
                    f"WHERE id = {_PG_PLACEHOLDER} AND user_id = {_PG_PLACEHOLDER}"
                )
                vals.extend([rid, str(scope_user_id)])
            cur = conn.cursor()
            cur.execute(sql, vals)
            return cur.rowcount > 0

    with _sqlite_connection() as conn:
        _init_schema_sqlite(conn)
        set_parts = [f"{k} = ?" for k in patch]
        vals = [_cell(patch, k) for k in patch]
        if scope_user_id is None:
            sql = f"UPDATE applications SET {', '.join(set_parts)} WHERE id = ?"
            vals.append(rid)
        else:
            sql = (
                f"UPDATE applications SET {', '.join(set_parts)} "
                "WHERE id = ? AND user_id = ?"
            )
            vals.extend([rid, str(scope_user_id)])
        cur = conn.cursor()
        cur.execute(sql, vals)
        return cur.rowcount > 0


def load_applications_db() -> pd.DataFrame:
    """Load all applications as DataFrame."""
    try:
        if _use_postgres():
            with _pg_connection() as conn:
                _init_schema_postgres(conn)
                df = pd.read_sql_query("SELECT * FROM applications ORDER BY applied_at DESC NULLS LAST", conn)
                return df.reindex(columns=TRACKER_COLUMNS, fill_value="")
        with _sqlite_connection() as conn:
            _init_schema_sqlite(conn)
            df = pd.read_sql_query("SELECT * FROM applications ORDER BY applied_at DESC", conn)
            return df.reindex(columns=TRACKER_COLUMNS, fill_value="")
    except Exception:
        return pd.DataFrame(columns=TRACKER_COLUMNS)


def save_applications_db(df: pd.DataFrame):
    """Replace all applications with DataFrame contents (for editor saves)."""
    cols = [c for c in TRACKER_COLUMNS if c in df.columns]
    if _use_postgres():
        with _pg_connection() as conn:
            _init_schema_postgres(conn)
            cur = conn.cursor()
            cur.execute("DELETE FROM applications")
            ph = ", ".join([_PG_PLACEHOLDER] * len(cols))
            sql = f"INSERT INTO applications ({', '.join(cols)}) VALUES ({ph})"
            for _, row in df.iterrows():
                vals = [_cell(row.to_dict(), c) for c in cols]
                cur.execute(sql, vals)
        return

    with _sqlite_connection() as conn:
        _init_schema_sqlite(conn)
        cur = conn.cursor()
        cur.execute("DELETE FROM applications")
        for _, row in df.iterrows():
            vals = [_cell(row.to_dict(), c) for c in cols]
            cur.execute(
                f"INSERT INTO applications ({', '.join(cols)}) VALUES ({', '.join('?'*len(cols))})",
                vals,
            )
