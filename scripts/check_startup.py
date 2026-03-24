#!/usr/bin/env python3
"""
Run Phase 3.5 startup validation without starting the API, worker, or Streamlit.

Uses the same rules as ``run_startup_checks()`` but does not call ``sys.exit`` unless
you pass ``--fail-on-errors`` / ``--fail-on-warnings`` (for CI).

Contexts:
  app       — FastAPI / API process
  worker    — Celery worker
  streamlit — UI process

Examples:
  PYTHONPATH=. python scripts/check_startup.py app
  PYTHONPATH=. python scripts/check_startup.py worker --fail-on-errors
  PYTHONPATH=. python scripts/check_startup.py streamlit --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))


def main() -> int:
    p = argparse.ArgumentParser(description="Print startup validation report (Phase 3.5)")
    p.add_argument(
        "context",
        nargs="?",
        default="app",
        choices=("app", "worker", "streamlit"),
        help="Which process profile to validate (default: app)",
    )
    p.add_argument(
        "--fail-on-errors",
        action="store_true",
        help="Exit 1 if any errors are reported",
    )
    p.add_argument(
        "--fail-on-warnings",
        action="store_true",
        help="Exit 1 if any warnings are reported",
    )
    p.add_argument("--json", action="store_true", help="Print errors and warnings as JSON")
    args = p.parse_args()

    try:
        from dotenv import load_dotenv

        load_dotenv(_ROOT / ".env")
    except ImportError:
        pass

    from services.startup_checks import collect_startup_report, is_strict_startup

    errors, warnings = collect_startup_report(args.context)
    strict = is_strict_startup()

    payload = {
        "context": args.context,
        "strict_startup_active": strict,
        "errors": errors,
        "warnings": warnings,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Startup check context={args.context!r} strict_startup_active={strict}")
        for e in errors:
            print(f"  ERROR: {e}")
        for w in warnings:
            print(f"  WARN:  {w}")
        if not errors and not warnings:
            print("  (no issues)")

    if args.fail_on_errors and errors:
        return 1
    if args.fail_on_warnings and warnings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
