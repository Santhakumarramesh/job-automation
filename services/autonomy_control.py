"""
Autonomy controls: file-backed overrides for live-submit kill switch.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _override_path() -> Path:
    raw = os.getenv("AUTONOMY_OVERRIDE_PATH", "").strip()
    if raw:
        return Path(raw)
    return PROJECT_ROOT / "autonomy_override.json"


def read_live_submit_pause_state() -> dict:
    path = _override_path()
    if not path.is_file():
        return {
            "paused": False,
            "reason": "",
            "updated_at": "",
            "updated_by": "",
            "source": "none",
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "paused": False,
            "reason": "",
            "updated_at": "",
            "updated_by": "",
            "source": "invalid",
        }
    return {
        "paused": bool(data.get("paused", False)),
        "reason": str(data.get("reason") or ""),
        "updated_at": str(data.get("updated_at") or ""),
        "updated_by": str(data.get("updated_by") or ""),
        "source": "file",
    }


def set_live_submit_paused(
    paused: bool,
    *,
    reason: str = "",
    updated_by: str = "operator",
) -> dict:
    path = _override_path()
    if not paused:
        try:
            if path.exists():
                path.unlink()
        except Exception:
            pass
        return {
            "paused": False,
            "reason": "",
            "updated_at": "",
            "updated_by": updated_by,
            "source": "cleared",
        }

    payload = {
        "paused": True,
        "reason": str(reason or "")[:500],
        "updated_at": datetime.now().isoformat(),
        "updated_by": str(updated_by or "")[:200],
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        pass
    return {**payload, "source": "file"}
