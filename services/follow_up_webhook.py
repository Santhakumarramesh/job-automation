"""
Optional HTTP webhook delivery for follow-up digest (Slack, Discord, or plain text).

Set FOLLOW_UP_WEBHOOK_URL. Default payload is Slack-compatible ``{"text": "..."}``.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Tuple

import requests

# Slack posts often cap around 4000 chars; stay under to avoid 400s.
_MAX_BODY_CHARS = 3500


def follow_up_webhook_configured() -> bool:
    return bool(os.getenv("FOLLOW_UP_WEBHOOK_URL", "").strip())


def _truncate_body(body: str) -> str:
    b = body.strip()
    if len(b) <= _MAX_BODY_CHARS:
        return b
    return b[: _MAX_BODY_CHARS - 24] + "\n...(digest truncated)"


def _merge_headers(base: Dict[str, str]) -> Dict[str, str]:
    h = dict(base)
    raw = os.getenv("FOLLOW_UP_WEBHOOK_HEADERS_JSON", "").strip()
    if not raw:
        return h
    try:
        extra = json.loads(raw)
        if isinstance(extra, dict):
            for k, v in extra.items():
                if k and v is not None:
                    h[str(k)] = str(v)
    except json.JSONDecodeError:
        pass
    return h


def send_follow_up_digest_webhook(body: str) -> Tuple[bool, str]:
    """
    POST digest to FOLLOW_UP_WEBHOOK_URL.
    FOLLOW_UP_WEBHOOK_STYLE: slack (default), discord, raw (text/plain).
    Optional: FOLLOW_UP_WEBHOOK_BEARER, FOLLOW_UP_WEBHOOK_HEADERS_JSON (object of extra headers).
    """
    url = os.getenv("FOLLOW_UP_WEBHOOK_URL", "").strip()
    if not url:
        return False, "Set FOLLOW_UP_WEBHOOK_URL"

    try:
        timeout = max(5, min(int(os.getenv("FOLLOW_UP_WEBHOOK_TIMEOUT", "30")), 120))
    except ValueError:
        timeout = 30

    style = os.getenv("FOLLOW_UP_WEBHOOK_STYLE", "slack").strip().lower()
    text = _truncate_body(body)

    bearer = os.getenv("FOLLOW_UP_WEBHOOK_BEARER", "").strip()
    headers: Dict[str, str] = {}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"

    try:
        if style == "raw":
            headers = _merge_headers(
                {**headers, "Content-Type": "text/plain; charset=utf-8"}
            )
            r = requests.post(
                url,
                data=text.encode("utf-8"),
                headers=headers,
                timeout=timeout,
            )
        else:
            payload: Dict[str, Any]
            if style == "discord":
                payload = {"content": text}
            elif style == "slack":
                payload = {"text": text}
            else:
                return False, f"Unknown FOLLOW_UP_WEBHOOK_STYLE={style!r} (use slack, discord, raw)"

            headers = _merge_headers({**headers, "Content-Type": "application/json"})
            r = requests.post(url, json=payload, headers=headers, timeout=timeout)

        if 200 <= r.status_code < 300:
            return True, f"ok HTTP {r.status_code}"
        return False, f"HTTP {r.status_code}: {r.text[:300]}"
    except requests.RequestException as e:
        return False, str(e)[:300]
