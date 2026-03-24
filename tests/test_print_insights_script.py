"""CLI scripts/print_insights.py"""

import json
import os
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch


def test_print_insights_json_output(monkeypatch):
    import sys

    monkeypatch.setenv("TRACKER_USE_DB", "0")
    import services.application_tracker as at

    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "job_applications.csv"
        prev = at.APPLICATION_FILE
        at.APPLICATION_FILE = csv_path
        try:
            at.initialize_tracker()
            at.log_application(
                {
                    "target_company": "Co",
                    "target_position": "Eng",
                    "job_id": "j1",
                    "user_id": "u1",
                    "policy_reason": "auto_easy_apply_all_checks_passed",
                }
            )
            import scripts.print_insights as pi

            old_argv = sys.argv
            buf = StringIO()
            try:
                sys.argv = ["print_insights.py", "--no-audit", "--json"]
                with patch.object(sys, "stdout", buf):
                    code = pi.main()
            finally:
                sys.argv = old_argv
            assert code == 0
            data = json.loads(buf.getvalue())
            assert "tracker" in data
            assert int(data["tracker"].get("total") or 0) >= 1
        finally:
            at.APPLICATION_FILE = prev
            os.environ.pop("TRACKER_USE_DB", None)


def test_text_report_contains_totals():
    from scripts.print_insights import _text_report

    sample = {
        "generated_at": "2026-01-01T00:00:00Z",
        "tracker": {"total": 3, "by_policy_reason": {"a": 2, "b": 1}, "ats": {"mean": 80.0, "count_numeric": 2}},
        "suggestions": ["hint one"],
        "answerer_review": {},
    }
    t = _text_report(sample)
    assert "tracker rows: 3" in t
    assert "hint one" in t
