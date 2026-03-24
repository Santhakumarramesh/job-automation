"""
Phase 3.3.3 — persist Celery/LangGraph task snapshots to disk (trimmed).

Workers can write checkpoints as the graph streams. Survives process restarts;
useful when Redis result backend evicts large payloads.

Env:
  TASK_STATE_DIR — default ``<project>/data/task_state``
  TASK_STATE_MAX_BYTES — max JSON file size (default 800_000)
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

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
    d = _task_state_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{task_id}.json"
    payload = {
        "task_id": task_id,
        "step": step,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "state": trim_state_for_storage(dict(state)),
    }
    raw = json.dumps(payload, default=str)
    path.write_text(raw[: _max_bytes()], encoding="utf-8")


def save_task_failure(
    task_id: str,
    message: str,
    failure_class: str,
    *,
    retries: int = 0,
) -> None:
    d = _task_state_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{task_id}.json"
    prev: dict = {}
    if path.is_file():
        try:
            prev = json.loads(path.read_text(encoding="utf-8"))
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
    path.write_text(json.dumps(prev, default=str)[: _max_bytes()], encoding="utf-8")


def load_task_snapshot(task_id: str) -> Optional[dict]:
    path = _task_state_dir() / f"{task_id}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
