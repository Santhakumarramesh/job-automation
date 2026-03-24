"""
Optional Telegram Bot API delivery for follow-up digest (sendMessage).

Requires FOLLOW_UP_TELEGRAM_BOT_TOKEN and FOLLOW_UP_TELEGRAM_CHAT_ID.
"""

from __future__ import annotations

import os
from typing import Tuple

import requests

# Telegram single-message limit; leave margin.
_MAX_BODY_CHARS = 4000


def follow_up_telegram_configured() -> bool:
    t = os.getenv("FOLLOW_UP_TELEGRAM_BOT_TOKEN", "").strip()
    c = os.getenv("FOLLOW_UP_TELEGRAM_CHAT_ID", "").strip()
    return bool(t and c)


def _truncate_body(body: str) -> str:
    b = body.strip()
    if len(b) <= _MAX_BODY_CHARS:
        return b
    return b[: _MAX_BODY_CHARS - 24] + "\n...(digest truncated)"


def send_follow_up_digest_telegram(body: str) -> Tuple[bool, str]:
    """
    POST to ``https://api.telegram.org/bot<token>/sendMessage``.
    Optional: FOLLOW_UP_TELEGRAM_TIMEOUT (seconds, default 30).
    No parse_mode — avoids Markdown/HTML breakage from arbitrary digest text.
    """
    token = os.getenv("FOLLOW_UP_TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("FOLLOW_UP_TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return False, "Set FOLLOW_UP_TELEGRAM_BOT_TOKEN and FOLLOW_UP_TELEGRAM_CHAT_ID"

    try:
        timeout = max(5, min(int(os.getenv("FOLLOW_UP_TELEGRAM_TIMEOUT", "30")), 120))
    except ValueError:
        timeout = 30

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": _truncate_body(body),
        "disable_web_page_preview": True,
    }

    try:
        r = requests.post(url, json=payload, timeout=timeout)
        data: dict = {}
        try:
            if r.text:
                parsed = r.json()
                if isinstance(parsed, dict):
                    data = parsed
        except ValueError:
            pass
        if r.ok and data.get("ok"):
            return True, "sent"
        err = str(data.get("description") or data.get("error_code") or "") if data else ""
        return False, f"HTTP {r.status_code}: {err or r.text[:300]}"
    except requests.RequestException as e:
        return False, str(e)[:300]
