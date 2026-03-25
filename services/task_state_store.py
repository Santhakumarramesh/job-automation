"""
Phase 3.3.3 / 4.2.2 — persist Celery/LangGraph task snapshots (trimmed).

Default: filesystem. Optional ``TASK_STATE_BACKEND=db`` (same DB URL as tracker /
idempotency) or ``TASK_STATE_BACKEND=s3`` (object store).

Env:
  TASK_STATE_DIR — default ``<project>/data/task_state`` (file backend)
  TASK_STATE_MAX_BYTES — max JSON file size (default 800_000)
  TASK_STATE_BACKEND — ``file`` (default), ``db``, or ``s3``
  TASK_STATE_S3_BUCKET — optional; falls back to ``ARTIFACTS_S3_BUCKET`` for s3 backend
  TASK_STATE_S3_PREFIX — S3 key prefix, default ``task_state``
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from services.tracker_db import _pg_connection, _sqlite_connection, _tracker_database_url, _use_postgres

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DIR = _PROJECT_ROOT / "data" / "task_state"

# Large text fields to truncate in snapshots
_TRIM_KEYS = (
    "base_resume_text",
    "job_description",
    "tailored_resume_text",
    "humanized_resume_text",
    "generated_project_text",
    "cover_letter_text",
    "humanized_cover_letter_text",
    "feedback",
)
_MAX_FIELD_LEN = 4000


def _task_state_dir() -> Path:
    raw = (os.getenv("TASK_STATE_DIR") or "").strip()
    return Path(raw) if raw else _DEFAULT_DIR


def _max_bytes() -> int:
    try:
        return max(10_000, int(os.getenv("TASK_STATE_MAX_BYTES", "800000")))
    except ValueError:
        return 800_000


def _raw_backend() -> str:
    return (os.getenv("TASK_STATE_BACKEND") or "file").strip().lower()


def can_use_db_for_task_state() -> bool:
    """True when TASK_STATE_BACKEND=db and tracker DB is reachable (Postgres or SQLite)."""
    if _raw_backend() != "db":
        return False
    url = _tracker_database_url()
    if url.startswith(("postgresql://", "postgres://")):
        return _use_postgres()
    return True


def _s3_bucket() -> str:
    return (os.getenv("TASK_STATE_S3_BUCKET") or os.getenv("ARTIFACTS_S3_BUCKET") or "").strip()


def _s3_prefix() -> str:
    p = (os.getenv("TASK_STATE_S3_PREFIX") or "task_state").strip().strip("/")
    return p


def can_use_s3_for_task_state() -> bool:
    return _raw_backend() == "s3" and bool(_s3_bucket())


def _effective_backend() -> str:
    b = _raw_backend()
    if b in ("file", "disk", "local", ""):
        return "file"
    if b == "db":
        return "db" if can_use_db_for_task_state() else "file"
    if b == "s3":
        return "s3" if can_use_s3_for_task_state() else "file"
    return "file"


def _safe_task_segment(task_id: str, max_len: int = 180) -> str:
    raw = re.sub(r"[^\w.\-]+", "_", str(task_id).strip())[:max_len]
    return raw or "task"


def _ensure_table_sqlite(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS task_state_snapshots (
            task_id TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def _ensure_table_pg(conn) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS task_state_snapshots (
            task_id TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def _save_file_raw(task_id: str, raw: str) -> None:
    d = _task_state_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{task_id}.json"
    path.write_text(raw, encoding="utf-8")


def _load_file_raw(task_id: str) -> Optional[str]:
    path = _task_state_dir() / f"{task_id}.json"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def _save_db_raw(task_id: str, raw: str) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    if _use_postgres():
        with _pg_connection() as conn:
            _ensure_table_pg(conn)
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO task_state_snapshots (task_id, payload, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (task_id) DO UPDATE SET
                    payload = EXCLUDED.payload,
                    updated_at = NOW()
                """,
                (task_id, raw),
            )
        return
    with _sqlite_connection() as conn:
        _ensure_table_sqlite(conn)
        conn.execute(
            """
            INSERT INTO task_state_snapshots (task_id, payload, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                payload = excluded.payload,
                updated_at = excluded.updated_at
            """,
            (task_id, raw, now_iso),
        )


def _load_db_raw(task_id: str) -> Optional[str]:
    if _use_postgres():
        with _pg_connection() as conn:
            _ensure_table_pg(conn)
            cur = conn.cursor()
            cur.execute(
                "SELECT payload FROM task_state_snapshots WHERE task_id = %s",
                (task_id,),
            )
            row = cur.fetchone()
            return str(row[0]) if row and row[0] is not None else None
    with _sqlite_connection() as conn:
        _ensure_table_sqlite(conn)
        cur = conn.execute(
            "SELECT payload FROM task_state_snapshots WHERE task_id = ?",
            (task_id,),
        )
        row = cur.fetchone()
        return str(row[0]) if row and row[0] is not None else None


def _s3_client():
    import boto3

    region = (
        os.getenv("AWS_REGION")
        or os.getenv("AWS_DEFAULT_REGION")
        or "us-east-1"
    ).strip()
    return boto3.client("s3", region_name=region)


def _s3_key(task_id: str) -> str:
    seg = _safe_task_segment(task_id)
    prefix = _s3_prefix()
    return f"{prefix}/{seg}.json" if prefix else f"{seg}.json"


def _save_s3_raw(task_id: str, raw: str) -> None:
    bucket = _s3_bucket()
    if not bucket:
        return
    cli = _s3_client()
    kwargs: Dict[str, Any] = {
        "Bucket": bucket,
        "Key": _s3_key(task_id),
        "Body": raw.encode("utf-8"),
    }
    sse = (os.getenv("ARTIFACTS_S3_SSE") or "").strip()
    if sse:
        kwargs["ServerSideEncryption"] = sse
    cli.put_object(**kwargs)


def _load_s3_raw(task_id: str) -> Optional[str]:
    bucket = _s3_bucket()
    if not bucket:
        return None
    try:
        cli = _s3_client()
        resp = cli.get_object(Bucket=bucket, Key=_s3_key(task_id))
        return resp["Body"].read().decode("utf-8")
    except Exception:
        return None


def _persist_raw(task_id: str, raw: str) -> None:
    if not task_id:
        return
    b = _effective_backend()
    if b == "file":
        _save_file_raw(task_id, raw)
    elif b == "db":
        _save_db_raw(task_id, raw)
    elif b == "s3":
        _save_s3_raw(task_id, raw)


def _load_raw(task_id: str) -> Optional[str]:
    if not task_id:
        return None
    b = _effective_backend()
    if b == "file":
        return _load_file_raw(task_id)
    if b == "db":
        return _load_db_raw(task_id)
    if b == "s3":
        return _load_s3_raw(task_id)
    return None


def trim_state_for_storage(state: Dict[str, Any]) -> Dict[str, Any]:
    """Copy state with long string fields truncated."""
    out: Dict[str, Any] = {}
    for k, v in state.items():
        if k in _TRIM_KEYS and isinstance(v, str) and len(v) > _MAX_FIELD_LEN:
            out[k] = v[:_MAX_FIELD_LEN] + "…[truncated]"
        else:
            out[k] = v
    return out


def save_task_snapshot(task_id: str, state: Dict[str, Any], *, step: str = "stream") -> None:
    """Write / overwrite snapshot for this Celery task id."""
    if not task_id:
        return
    payload = {
        "task_id": task_id,
        "step": step,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "state": trim_state_for_storage(dict(state)),
    }
    raw = json.dumps(payload, default=str)[: _max_bytes()]
    _persist_raw(task_id, raw)


def save_task_failure(
    task_id: str,
    message: str,
    failure_class: str,
    *,
    retries: int = 0,
) -> None:
    prev: dict = {}
    raw_prev = _load_raw(task_id)
    if raw_prev:
        try:
            prev = json.loads(raw_prev)
        except json.JSONDecodeError:
            prev = {}
    prev.update(
        {
            "task_id": task_id,
            "step": "failed",
            "failure_class": failure_class,
            "error_message": (message or "")[:8000],
            "retries": retries,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    raw = json.dumps(prev, default=str)[: _max_bytes()]
    _persist_raw(task_id, raw)


def load_task_snapshot(task_id: str) -> Optional[dict]:
    raw = _load_raw(task_id)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None
