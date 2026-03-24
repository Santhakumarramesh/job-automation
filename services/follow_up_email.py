"""
Optional SMTP delivery for follow-up digest (cron / GitHub Actions).

Set FOLLOW_UP_SMTP_HOST and FOLLOW_UP_EMAIL_TO at minimum; see docs/FOLLOW_UPS.md.
"""

from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText
from typing import Optional, Tuple


def follow_up_smtp_configured() -> bool:
    host = os.getenv("FOLLOW_UP_SMTP_HOST", "").strip()
    to = os.getenv("FOLLOW_UP_EMAIL_TO", "").strip()
    return bool(host and to)


def send_follow_up_digest_email(
    body: str,
    *,
    subject: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Send plain-text email. Returns (ok, message).
    """
    host = os.getenv("FOLLOW_UP_SMTP_HOST", "").strip()
    to_addr = os.getenv("FOLLOW_UP_EMAIL_TO", "").strip()
    if not host or not to_addr:
        return False, "Set FOLLOW_UP_SMTP_HOST and FOLLOW_UP_EMAIL_TO"

    try:
        port = int(os.getenv("FOLLOW_UP_SMTP_PORT", "587"))
    except ValueError:
        port = 587

    user = os.getenv("FOLLOW_UP_SMTP_USER", "").strip()
    password = os.getenv("FOLLOW_UP_SMTP_PASSWORD", "") or ""
    from_addr = (os.getenv("FOLLOW_UP_EMAIL_FROM") or user or to_addr).strip()
    subj = subject or os.getenv("FOLLOW_UP_EMAIL_SUBJECT", "Job follow-up reminders").strip()
    use_tls = os.getenv("FOLLOW_UP_SMTP_USE_TLS", "1").lower() in ("1", "true", "yes")

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subj
    msg["From"] = from_addr
    msg["To"] = to_addr

    try:
        with smtplib.SMTP(host, port, timeout=45) as server:
            if use_tls:
                server.starttls()
            if user:
                server.login(user, password)
            server.sendmail(from_addr, [to_addr], msg.as_string())
        return True, "sent"
    except Exception as e:
        return False, str(e)[:300]
