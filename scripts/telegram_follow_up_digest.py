#!/usr/bin/env python3
"""
Send due follow-ups to Telegram via Bot API (sendMessage).

Requires env (see docs/FOLLOW_UPS.md):
  FOLLOW_UP_TELEGRAM_BOT_TOKEN, FOLLOW_UP_TELEGRAM_CHAT_ID
Optional:
  FOLLOW_UP_TELEGRAM_TIMEOUT (seconds)

Examples:
  PYTHONPATH=. python scripts/telegram_follow_up_digest.py --dry-run
  PYTHONPATH=. python scripts/telegram_follow_up_digest.py --user-id streamlit-local
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))


def main() -> int:
    p = argparse.ArgumentParser(description="Send follow-up digest to Telegram")
    p.add_argument("--user-id", default="", help="Tracker user_id filter; empty = all rows")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print digest and whether Telegram env is configured; do not send",
    )
    args = p.parse_args()

    try:
        from dotenv import load_dotenv

        load_dotenv(_ROOT / ".env")
    except ImportError:
        pass

    from services.follow_up_service import format_follow_up_digest, list_follow_ups
    from services.follow_up_telegram import follow_up_telegram_configured, send_follow_up_digest_telegram

    uid = args.user_id.strip() or None
    items = list_follow_ups(uid, due_only=True, limit=max(1, min(args.limit, 200)))
    text = format_follow_up_digest(items)

    if args.dry_run:
        print(text)
        print("---")
        print(f"Telegram configured: {follow_up_telegram_configured()}")
        return 0

    if not follow_up_telegram_configured():
        print(
            "Set FOLLOW_UP_TELEGRAM_BOT_TOKEN and FOLLOW_UP_TELEGRAM_CHAT_ID, or use --dry-run",
            file=sys.stderr,
        )
        return 2

    if not items:
        print("No due follow-ups; skipping send.")
        return 0

    ok, msg = send_follow_up_digest_telegram(text)
    if ok:
        print(f"Sent digest ({len(items)} items).")
        return 0
    print(f"Send failed: {msg}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
