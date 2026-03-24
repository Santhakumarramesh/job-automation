#!/usr/bin/env python3
"""
POST due follow-ups to an HTTP webhook (Slack incoming webhook, Discord, or raw text).

Requires env (see docs/FOLLOW_UPS.md):
  FOLLOW_UP_WEBHOOK_URL
Optional:
  FOLLOW_UP_WEBHOOK_STYLE=slack|discord|raw (default slack)
  FOLLOW_UP_WEBHOOK_BEARER, FOLLOW_UP_WEBHOOK_HEADERS_JSON, FOLLOW_UP_WEBHOOK_TIMEOUT

Examples:
  PYTHONPATH=. python scripts/webhook_follow_up_digest.py --dry-run
  PYTHONPATH=. python scripts/webhook_follow_up_digest.py --user-id streamlit-local
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))


def main() -> int:
    p = argparse.ArgumentParser(description="POST follow-up digest to webhook URL")
    p.add_argument("--user-id", default="", help="Tracker user_id filter; empty = all rows")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print digest and webhook config only; do not POST",
    )
    args = p.parse_args()

    try:
        from dotenv import load_dotenv

        load_dotenv(_ROOT / ".env")
    except ImportError:
        pass

    from services.follow_up_webhook import follow_up_webhook_configured, send_follow_up_digest_webhook
    from services.follow_up_service import format_follow_up_digest, list_follow_ups

    uid = args.user_id.strip() or None
    items = list_follow_ups(uid, due_only=True, limit=max(1, min(args.limit, 200)))
    text = format_follow_up_digest(items)

    if args.dry_run:
        print(text)
        print("---")
        print(f"Webhook configured: {follow_up_webhook_configured()}")
        return 0

    if not follow_up_webhook_configured():
        print("Set FOLLOW_UP_WEBHOOK_URL, or use --dry-run", file=sys.stderr)
        return 2

    if not items:
        print("No due follow-ups; skipping POST.")
        return 0

    ok, msg = send_follow_up_digest_webhook(text)
    if ok:
        print(f"Posted digest ({len(items)} items). {msg}")
        return 0
    print(f"POST failed: {msg}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
