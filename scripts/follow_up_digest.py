#!/usr/bin/env python3
"""
Print due follow-ups as plain text (cron, email paste, Slack).
Uses tracker CSV/DB like the API. No auth — run locally.

Examples:
  PYTHONPATH=. python scripts/follow_up_digest.py
  PYTHONPATH=. python scripts/follow_up_digest.py --user-id streamlit-local
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))


def main() -> None:
    p = argparse.ArgumentParser(description="Plain-text digest of due follow-ups")
    p.add_argument(
        "--user-id",
        default="",
        help="Filter by tracker user_id; omit or empty for all rows (local use).",
    )
    p.add_argument("--limit", type=int, default=50, help="Max rows (default 50)")
    args = p.parse_args()
    try:
        from dotenv import load_dotenv

        load_dotenv(_ROOT / ".env")
    except ImportError:
        pass
    from services.follow_up_service import format_follow_up_digest, list_follow_ups

    uid = args.user_id.strip() or None
    items = list_follow_ups(uid, due_only=True, limit=max(1, min(args.limit, 200)))
    sys.stdout.write(format_follow_up_digest(items))


if __name__ == "__main__":
    main()
