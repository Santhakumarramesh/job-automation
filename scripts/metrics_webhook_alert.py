#!/usr/bin/env python3
"""
POST a JSON alert when Redis Celery metrics cross operator thresholds (Phase 4.3.3).

Requires workers to increment metrics (CELERY_METRICS_REDIS=1) and this process to
read the same Redis (REDIS_METRICS_URL or REDIS_BROKER).

Env (see services/metrics_alert_webhook.py):
  METRICS_ALERT_WEBHOOK_URL
  METRICS_ALERT_ERROR_TOTAL_MIN, METRICS_ALERT_ERROR_PERMANENT_MIN, …
  METRICS_ALERT_COOLDOWN_SECONDS (default 3600)
  CELERY_METRICS_REDIS=1

Examples:
  PYTHONPATH=. python scripts/metrics_webhook_alert.py --dry-run
  CELERY_METRICS_REDIS=1 METRICS_ALERT_ERROR_TOTAL_MIN=1 METRICS_ALERT_WEBHOOK_URL=https://hooks.slack.com/... \\
    PYTHONPATH=. python scripts/metrics_webhook_alert.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))


def main() -> int:
    p = argparse.ArgumentParser(description="Webhook alert when Celery Redis metrics exceed thresholds")
    p.add_argument("--dry-run", action="store_true", help="Print payload only; do not POST")
    args = p.parse_args()

    try:
        from dotenv import load_dotenv

        load_dotenv(_ROOT / ".env")
    except ImportError:
        pass

    from services.metrics_alert_webhook import run_metrics_webhook_alert

    code, msg = run_metrics_webhook_alert(dry_run=args.dry_run)
    print(msg)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
