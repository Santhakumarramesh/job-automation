"""
Phase 4.2.1 — database-backed idempotent job enqueue (Postgres or SQLite).

Set ``IDEMPOTENCY_USE_DB=1``. Uses the same DB URL as the tracker
(``TRACKER_DATABASE_URL`` / ``DATABASE_URL``). Postgres requires
``TRACKER_USE_DB=1`` (same as tracker). SQLite uses the configured SQLite file.

Inserts a row **before** ``apply_async`` so concurrent API replicas cannot enqueue
duplicate Celery tasks for the same (user_id, idempotency_key).

Env:
  IDEMPOTENCY_USE_DB — ``1`` / ``true`` / ``yes`` to enable
  IDEMPOTENCY_TTL_HOURS — same TTL as file backend (default 24)
"""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

import sqlite3

from services.tracker_db import _pg_connection, _sqlite_connection, _tracker_database_url, _use_postgres


def idempotency_db_requested() -> bool:
    return os.getenv("IDEMPOTENCY_USE_DB", "").strip().lower() in ("1", "true", "yes")


def can_use_db_for_idempotency() -> bool:
    if not idempotency_db_requested():
        return False
    url = _tracker_database_url()
    if url.startswith(("postgresql://", "postgres://")):
        return _use_postgres()
    # SQLite URL, or empty URL (tracker default ``job_applications.db``)
    return True


def _ttl_hours() -> float:
    try:
        return max(0.1, float(os.getenv("IDEMPOTENCY_TTL_HOURS", "24")))
    except ValueError:
        return 24.0


def _digest(user_id: str, idempotency_key: str) -> str:
    return hashlib.sha256(f"{user_id}\n{idempotency_key}".encode("utf-8")).hexdigest()[:48]


def _parse_ts(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _age_hours(created: datetime) -> float:
    return (datetime.now(timezone.utc) - created).total_seconds() / 3600.0


def _ensure_table_sqlite(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS job_idempotency (
            user_id TEXT NOT NULL,
            key_digest TEXT NOT NULL,
            job_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (user_id, key_digest)
        )
        """
    )


def _ensure_table_pg(conn) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS job_idempotency (
            user_id TEXT NOT NULL,
            key_digest TEXT NOT NULL,
            job_id TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, key_digest)
        )
        """
    )


def _delete_expired_sqlite(conn, user_id: str, digest: str) -> None:
    cur = conn.execute(
        "SELECT created_at FROM job_idempotency WHERE user_id = ? AND key_digest = ?",
        (user_id, digest),
    )
    row = cur.fetchone()
    if not row:
        return
    created = _parse_ts(row[0])
    if created is None or _age_hours(created) <= _ttl_hours():
        return
    conn.execute(
        "DELETE FROM job_idempotency WHERE user_id = ? AND key_digest = ?",
        (user_id, digest),
    )


def _delete_expired_pg(conn, user_id: str, digest: str) -> None:
    cur = conn.cursor()
    cur.execute(
        "SELECT created_at FROM job_idempotency WHERE user_id = %s AND key_digest = %s",
        (user_id, digest),
    )
    row = cur.fetchone()
    if not row:
        return
    created = row[0]
    if created is None:
        return
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    if _age_hours(created) <= _ttl_hours():
        return
    cur.execute(
        "DELETE FROM job_idempotency WHERE user_id = %s AND key_digest = %s",
        (user_id, digest),
    )


def _lookup_valid_sqlite(conn, user_id: str, digest: str) -> Optional[str]:
    _delete_expired_sqlite(conn, user_id, digest)
    cur = conn.execute(
        "SELECT job_id, created_at FROM job_idempotency WHERE user_id = ? AND key_digest = ?",
        (user_id, digest),
    )
    row = cur.fetchone()
    if not row:
        return None
    jid, created_raw = row[0], row[1]
    created = _parse_ts(str(created_raw))
    if created is None or _age_hours(created) > _ttl_hours():
        conn.execute(
            "DELETE FROM job_idempotency WHERE user_id = ? AND key_digest = ?",
            (user_id, digest),
        )
        return None
    return str(jid).strip() if jid else None


def _lookup_valid_pg(conn, user_id: str, digest: str) -> Optional[str]:
    _delete_expired_pg(conn, user_id, digest)
    cur = conn.cursor()
    cur.execute(
        "SELECT job_id, created_at FROM job_idempotency WHERE user_id = %s AND key_digest = %s",
        (user_id, digest),
    )
    row = cur.fetchone()
    if not row:
        return None
    jid, created = row[0], row[1]
    if created is None:
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    if _age_hours(created) > _ttl_hours():
        cur.execute(
            "DELETE FROM job_idempotency WHERE user_id = %s AND key_digest = %s",
            (user_id, digest),
        )
        return None
    return str(jid).strip() if jid else None


def resolve_enqueue_with_db(user_id: str, idempotency_key: str) -> Tuple[str, bool]:
    """
    Atomically reserve or return existing Celery task id.

    Returns ``(job_id, should_enqueue)``. When ``should_enqueue`` is False, the
    caller must not call ``apply_async`` (duplicate key).
    """
    if not can_use_db_for_idempotency():
        raise RuntimeError("DB idempotency not available (check IDEMPOTENCY_USE_DB and DB URL)")

    digest = _digest(user_id, idempotency_key)
    if _use_postgres():
        with _pg_connection() as conn:
            _ensure_table_pg(conn)
            existing = _lookup_valid_pg(conn, user_id, digest)
            if existing:
                return existing, False
            new_id = str(uuid.uuid4())
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    INSERT INTO job_idempotency (user_id, key_digest, job_id, created_at)
                    VALUES (%s, %s, %s, NOW())
                    """,
                    (user_id, digest, new_id),
                )
                return new_id, True
            except Exception as e:
                import psycopg2

                if not isinstance(e, psycopg2.IntegrityError):
                    raise
                existing2 = _lookup_valid_pg(conn, user_id, digest)
                if existing2:
                    return existing2, False
                raise RuntimeError("idempotency insert conflict but no row found") from e

    with _sqlite_connection() as conn:
        _ensure_table_sqlite(conn)
        existing = _lookup_valid_sqlite(conn, user_id, digest)
        if existing:
            return existing, False
        new_id = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            conn.execute(
                """
                INSERT INTO job_idempotency (user_id, key_digest, job_id, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, digest, new_id, now_iso),
            )
            return new_id, True
        except sqlite3.IntegrityError as e:
            existing2 = _lookup_valid_sqlite(conn, user_id, digest)
            if existing2:
                return existing2, False
            raise RuntimeError("idempotency insert conflict but no row found") from e
