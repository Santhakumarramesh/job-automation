"""scripts/check_startup.py"""

import json
import sys
from io import StringIO
from unittest.mock import patch


def _run(argv: list[str]):
    import scripts.check_startup as cs

    old = sys.argv
    buf = StringIO()
    try:
        sys.argv = ["check_startup.py"] + argv
        with patch.object(sys, "stdout", buf):
            code = cs.main()
        return code, buf.getvalue()
    finally:
        sys.argv = old


def test_check_startup_json(monkeypatch):
    monkeypatch.delenv("AWS_SECRETS_MANAGER_SECRET_ID", raising=False)
    code, out = _run(["app", "--json"])
    assert code == 0
    data = json.loads(out)
    assert data["context"] == "app"
    assert "errors" in data and "warnings" in data


def test_fail_on_warnings(monkeypatch):
    monkeypatch.delenv("AWS_SECRETS_MANAGER_SECRET_ID", raising=False)

    def fake_report(ctx: str):
        return [], ["test warning only"]

    with patch("services.startup_checks.collect_startup_report", fake_report):
        code, out = _run(["app", "--fail-on-warnings"])
    assert code == 1
    assert "test warning" in out
