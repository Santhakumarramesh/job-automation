#!/usr/bin/env python3
"""
Deliver the due follow-up digest through every configured channel (one cron entry).

Uses the same env vars as:
  scripts/email_follow_up_digest.py (SMTP)
  scripts/webhook_follow_up_digest.py (FOLLOW_UP_WEBHOOK_*)
  scripts/telegram_follow_up_digest.py (FOLLOW_UP_TELEGRAM_*)

Delivery order: webhook → Telegram → email (push-style first).

Examples:
  PYTHONPATH=. python scripts/notify_follow_up_digest.py --dry-run
  PYTHONPATH=. python scripts/notify_follow_up_digest.py --user-id streamlit-local
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable, List, Tuple

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(_ROOT / ".env")
    except ImportError:
        pass


def main() -> int:
    p = argparse.ArgumentParser(
        description="Send follow-up digest via all configured channels (webhook, Telegram, SMTP)",
    )
    p.add_argument("--user-id", default="", help="Tracker user_id filter; empty = all rows")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print digest and which channels are configured; do not send",
    )
    args = p.parse_args()
    _load_env()

    from services.follow_up_email import follow_up_smtp_configured, send_follow_up_digest_email
    from services.follow_up_service import format_follow_up_digest, list_follow_ups
    from services.follow_up_telegram import follow_up_telegram_configured, send_follow_up_digest_telegram
    from services.follow_up_webhook import follow_up_webhook_configured, send_follow_up_digest_webhook

    uid = args.user_id.strip() or None
    items = list_follow_ups(uid, due_only=True, limit=max(1, min(args.limit, 200)))
    text = format_follow_up_digest(items)

    wh_ok = follow_up_webhook_configured()
    tg_ok = follow_up_telegram_configured()
    sm_ok = follow_up_smtp_configured()

    if args.dry_run:
        print(text)
        print("---")
        print(f"Webhook:  {wh_ok}")
        print(f"Telegram: {tg_ok}")
        print(f"SMTP:     {sm_ok}")
        return 0

    if not items:
        print("No due follow-ups; nothing to send.")
        return 0

    channels: List[Tuple[str, Callable[[str], Tuple[bool, str]]]] = []
    if wh_ok:
        channels.append(("webhook", send_follow_up_digest_webhook))
    if tg_ok:
        channels.append(("telegram", send_follow_up_digest_telegram))
    if sm_ok:
        channels.append(("smtp", send_follow_up_digest_email))

    if not channels:
        print(
            "No delivery channels configured. Set FOLLOW_UP_WEBHOOK_URL and/or "
            "FOLLOW_UP_TELEGRAM_BOT_TOKEN+CHAT_ID and/or FOLLOW_UP_SMTP_HOST+EMAIL_TO "
            "(see docs/FOLLOW_UPS.md), or use --dry-run.",
            file=sys.stderr,
        )
        return 2

    failures: List[str] = []
    for name, send in channels:
        ok, msg = send(text)
        if ok:
            print(f"{name}: ok ({msg})")
        else:
            failures.append(f"{name}: {msg}")
            print(f"{name}: FAILED {msg}", file=sys.stderr)

    if failures:
        return 1
    print(f"All channels ok ({len(items)} items).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
