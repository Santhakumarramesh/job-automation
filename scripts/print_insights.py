#!/usr/bin/env python3
"""
Print Phase 13 application insights from the local tracker (no FastAPI).

Same data shape as GET /api/insights (minus HTTP auth scope — you choose user_id filter).

Examples:
  PYTHONPATH=. python scripts/print_insights.py
  PYTHONPATH=. python scripts/print_insights.py --json > insights.json
  PYTHONPATH=. python scripts/print_insights.py --user-id streamlit-local --no-audit
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))


def _text_report(payload: Dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"generated_at: {payload.get('generated_at', '')}")
    tr = payload.get("tracker") or {}
    lines.append(f"tracker rows: {tr.get('total', 0)}")
    ats = tr.get("ats") or {}
    if ats.get("mean") is not None:
        lines.append(f"ATS (logged): mean={ats.get('mean')} n={ats.get('count_numeric')}")

    def _top(title: str, d: Any, n: int = 8) -> None:
        if not isinstance(d, dict) or not d:
            return
        lines.append(f"\n{title}:")
        for k, v in sorted(d.items(), key=lambda x: -x[1])[:n]:
            lines.append(f"  {k}: {v}")

    _top("policy_reason", tr.get("by_policy_reason"))
    _top("submission_status", tr.get("by_submission_status"))
    _top("apply_mode", tr.get("by_apply_mode"))

    xt = tr.get("crosstabs") or {}
    sp = xt.get("submission_status_by_policy_reason") or []
    if sp:
        lines.append("\nsubmission × policy (top pairs):")
        for row in sp[:10]:
            if isinstance(row, dict):
                lines.append(
                    f"  {row.get('submission_status')} + {row.get('policy_reason')}: {row.get('count')}"
                )

    ar = payload.get("answerer_review") or {}
    if ar.get("tracker_rows_with_answerer_review"):
        lines.append(
            f"\nanswerer QA rows: {ar.get('tracker_rows_with_answerer_review')} "
            f"(manual_review: {ar.get('tracker_rows_with_manual_review_flag', 0)})"
        )

    aud = payload.get("audit")
    if isinstance(aud, dict) and aud.get("events_included"):
        lines.append(f"\naudit tail: {aud.get('events_included')} events")
        fc = aud.get("failure_class") or {}
        if fc:
            lines.append(f"  failure_class: {dict(list(fc.items())[:5])}")

    sug = payload.get("suggestions") or []
    if sug:
        lines.append("\nsuggestions:")
        for s in sug:
            lines.append(f"  - {s}")

    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description="Print application insights from local tracker")
    p.add_argument(
        "--user-id",
        default="",
        help="Tracker user_id filter; empty = all rows. Default: env TRACKER_DEFAULT_USER_ID if set.",
    )
    p.add_argument("--no-audit", action="store_true", help="Skip audit JSONL summary")
    p.add_argument("--audit-max-lines", type=int, default=2500)
    p.add_argument("--json", action="store_true", help="Print full JSON (API-shaped payload)")
    args = p.parse_args()

    try:
        from dotenv import load_dotenv

        load_dotenv(_ROOT / ".env")
    except ImportError:
        pass

    uid = (args.user_id or os.getenv("TRACKER_DEFAULT_USER_ID") or "").strip() or None

    from services.application_insights import build_application_insights

    payload = build_application_insights(
        uid,
        include_audit=not args.no_audit,
        audit_max_lines=max(100, min(args.audit_max_lines, 50_000)),
    )

    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        sys.stdout.write(_text_report(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
