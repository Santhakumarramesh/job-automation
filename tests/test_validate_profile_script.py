"""scripts/validate_profile.py"""

import json
import sys
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch


def _run_main(argv: list[str]):
    import scripts.validate_profile as vp

    old = sys.argv
    buf = StringIO()
    try:
        sys.argv = ["validate_profile.py"] + argv
        with patch.object(sys, "stdout", buf):
            code = vp.main()
        return code, buf.getvalue()
    finally:
        sys.argv = old


def test_validate_profile_not_ready_exit_1():
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"full_name": "A", "email": "a@b.co"}, f)
        f.flush()
        path = f.name
    try:
        code, out = _run_main(["--path", path])
        assert code == 1
        assert "auto_apply_ready: False" in out or "auto_apply_ready: false".lower() in out.lower()
    finally:
        Path(path).unlink(missing_ok=True)


def test_validate_profile_json_mode():
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"full_name": "A", "email": "a@b.co"}, f)
        f.flush()
        path = f.name
    try:
        code, out = _run_main(["--path", path, "--json"])
        assert code == 1
        data = json.loads(out)
        assert data["auto_apply_ready"] is False
        assert "phone" in " ".join(data.get("missing_auto_apply_fields") or []).lower() or any(
            "phone" in x for x in (data.get("missing_auto_apply_fields") or [])
        )
    finally:
        Path(path).unlink(missing_ok=True)


def test_validate_profile_strict_warnings():
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        d = {
            "full_name": "Test User",
            "email": "t@example.com",
            "phone": "+1 555",
            "linkedin_url": "https://linkedin.com/in/x",
            "work_authorization_note": "US auth",
            "notice_period": "2 weeks",
            "short_answers": {},
            "application_locations": "should_be_list",
        }
        json.dump(d, f)
        f.flush()
        path = f.name
    try:
        code, out = _run_main(["--path", path, "--strict"])
        assert code == 1
        assert "application_locations" in out.lower() or "warning" in out.lower() or "⚠️" in out
    finally:
        Path(path).unlink(missing_ok=True)
