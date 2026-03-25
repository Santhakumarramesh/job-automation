"""
Structured logging helpers, correlation ID, and append-only audit log (JSONL).
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
AUDIT_LOG_PATH = Path(os.getenv("AUDIT_LOG_PATH", str(_PROJECT_ROOT / "application_audit.jsonl")))


def _ensure_audit_dir() -> None:
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def audit_log(
    action: str,
    job_id: str = "",
    company: str = "",
    position: str = "",
    status: str = "",
    correlation_id: str = "",
    extra: Optional[dict] = None,
) -> None:
    """
    Append one JSON line for apply / tracker events.
    action examples: apply_started, apply_completed, apply_skipped, apply_failed, tracker_logged
    """
    event = {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "action": action,
        "job_id": job_id,
        "company": company,
        "position": position,
        "status": status,
        "correlation_id": correlation_id,
        **(extra or {}),
    }
    try:
        _ensure_audit_dir()
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, default=str) + "\n")
    except Exception:
        pass


def configure_structured_logging() -> None:
    """When LOG_JSON=1, root logger emits JSON lines."""
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    use_json = os.getenv("LOG_JSON", "0").lower() in ("1", "true", "yes")
    handler = logging.StreamHandler()
    handler.setFormatter(
        _StructuredFormatter() if use_json else logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    )
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(handler)
    root.setLevel(getattr(logging, level, logging.INFO))


class _StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        d = {
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if hasattr(record, "correlation_id"):
            d["correlation_id"] = record.correlation_id
        if record.exc_info:
            d["exception"] = self.formatException(record.exc_info)
        return json.dumps(d, default=str)


def get_or_create_correlation_id(request_id_header: Optional[str] = None) -> str:
    """Use X-Request-ID from client or generate a UUID."""
    if request_id_header:
        return request_id_header.strip()[:128]
    return str(uuid.uuid4())
