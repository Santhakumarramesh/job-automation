#!/usr/bin/env python3
"""
Validate config/candidate_profile.json (or CANDIDATE_PROFILE_PATH) for apply + answerer use.

Exit codes:
  0 — auto-apply ready and (no warnings, or --strict not set)
  1 — not auto-apply ready, or --strict and any validation warnings

Examples:
  PYTHONPATH=. python scripts/validate_profile.py
  PYTHONPATH=. python scripts/validate_profile.py --path config/candidate_profile.json --strict
  PYTHONPATH=. python scripts/validate_profile.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))


def main() -> int:
    p = argparse.ArgumentParser(description="Validate candidate profile JSON")
    p.add_argument(
        "--path",
        default="",
        help="Profile JSON path (default: CANDIDATE_PROFILE_PATH or config/candidate_profile.json)",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 if validate_profile reports any warnings (shape, URLs, etc.)",
    )
    p.add_argument("--json", action="store_true", help="Print machine-readable summary to stdout")
    args = p.parse_args()

    try:
        from dotenv import load_dotenv

        load_dotenv(_ROOT / ".env")
    except ImportError:
        pass

    from services.profile_service import (
        AUTO_APPLY_REQUIRED,
        DEFAULT_PROFILE_PATH,
        is_auto_apply_ready,
        load_profile,
        validate_profile,
    )

    path_arg = args.path.strip() or None
    prof = load_profile(path_arg)
    resolved = path_arg or str(DEFAULT_PROFILE_PATH)

    warnings = validate_profile(prof)
    ready = is_auto_apply_ready(prof)

    missing_auto = [k for k in AUTO_APPLY_REQUIRED if not str(prof.get(k) or "").strip()]

    out = {
        "profile_path_resolved": resolved,
        "auto_apply_ready": ready,
        "missing_auto_apply_fields": missing_auto,
        "warnings": warnings,
    }

    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"Profile: {resolved}")
        print(f"auto_apply_ready: {ready}")
        if missing_auto:
            print("Missing for auto-apply:", ", ".join(missing_auto))
        if warnings:
            for w in warnings:
                print(f"  ⚠️ {w}")
        elif not args.json:
            print("  (no validation warnings)")

    if not ready:
        return 1
    if args.strict and warnings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
