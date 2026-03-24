"""
Phase 3.3.2 — idempotent job enqueue (file-backed by default).

Same (user_id, idempotency_key) within TTL returns the original task id.
The API accepts the key as JSON ``idempotency_key`` or ``Idempotency-Key`` header (see ``app.main``).

Phase 4.2.1: set ``IDEMPOTENCY_USE_DB=1`` for database-backed keys (see ``services.idempotency_db``).

Env:
  IDEMPOTENCY_DIR — default ``<project>/data/idempotency``
  IDEMPOTENCY_TTL_HOURS — default 24
  IDEMPOTENCY_USE_DB — ``1`` to use tracker DB (Postgres or SQLite)
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DIR = _PROJECT_ROOT / "data" / "idempotency"


def _dir() -> Path:
    raw = (os.getenv("IDEMPOTENCY_DIR") or "").strip()
    return Path(raw) if raw else _DEFAULT_DIR


def _ttl_hours() -> float:
    try:
        return max(0.1, float(os.getenv("IDEMPOTENCY_TTL_HOURS", "24")))
    except ValueError:
        return 24.0


def _key_path(user_id: str, idempotency_key: str) -> Path:
    h = hashlib.sha256(f"{user_id}\n{idempotency_key}".encode("utf-8")).hexdigest()[:48]
    return _dir() / f"{h}.json"


def _parse_iso(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def lookup_idempotent_job(user_id: str, idempotency_key: str) -> Optional[str]:
    """Return existing Celery task id if key is still valid, else None."""
    key = (idempotency_key or "").strip()
    if not key:
        return None
    path = _key_path(user_id, key)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    created = _parse_iso(data.get("created_at", ""))
    if created is None:
        return None
    age_h = (datetime.now(timezone.utc) - created).total_seconds() / 3600.0
    if age_h > _ttl_hours():
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return None
    jid = data.get("job_id")
    return str(jid).strip() if jid else None


def uses_db_for_idempotency() -> bool:
    """True when enqueue should claim keys in the database (not the file store)."""
    try:
        from services.idempotency_db import can_use_db_for_idempotency

        return can_use_db_for_idempotency()
    except Exception:
        return False


def resolve_idempotent_enqueue(user_id: str, idempotency_key: str) -> Tuple[str, bool]:
    """
    Returns ``(celery_task_id, should_apply_async)``.
    When ``should_apply_async`` is False, the task id already exists — do not enqueue again.
    """
    key = (idempotency_key or "").strip()
    if not key:
        return str(uuid.uuid4()), True
    if uses_db_for_idempotency():
        from services.idempotency_db import resolve_enqueue_with_db

        return resolve_enqueue_with_db(user_id, key)
    existing = lookup_idempotent_job(user_id, key)
    if existing:
        return existing, False
    return str(uuid.uuid4()), True


def store_idempotent_job(user_id: str, idempotency_key: str, job_id: str) -> None:
    key = (idempotency_key or "").strip()
    if not key:
        return
    if uses_db_for_idempotency():
        return
    _dir().mkdir(parents=True, exist_ok=True)
    path = _key_path(user_id, key)
    path.write_text(
        json.dumps(
            {
                "user_id": user_id,
                "idempotency_key": key,
                "job_id": job_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=0,
        ),
        encoding="utf-8",
    )
