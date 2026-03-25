"""truth_apply_gate — profile readiness before live LinkedIn apply."""

from unittest.mock import patch

from services.truth_apply_gate import (
    assess_truth_apply_profile,
    truth_apply_hard_gate_enabled,
    truth_apply_live_blocked_message,
)


def test_assess_empty_profile_not_ok():
    a = assess_truth_apply_profile({})
    assert a["ok"] is False
    assert a["auto_apply_ready"] is False
    assert "full_name" in (a.get("missing_required_fields") or [])


def test_assess_minimal_complete_ok():
    p = {
        "full_name": "A B",
        "email": "a@b.co",
        "phone": "1",
        "linkedin_url": "https://linkedin.com/in/x",
        "work_authorization_note": "US citizen",
        "notice_period": "2 weeks",
    }
    a = assess_truth_apply_profile(p)
    assert a["ok"] is True
    assert a["auto_apply_ready"] is True
    assert not a.get("missing_required_fields")


def test_live_blocked_only_when_gate_on_and_live(monkeypatch):
    monkeypatch.delenv("TRUTH_APPLY_HARD_GATE", raising=False)
    assert truth_apply_live_blocked_message({}, dry_run=False, shadow_mode=False) is None
    monkeypatch.setenv("TRUTH_APPLY_HARD_GATE", "1")
    msg = truth_apply_live_blocked_message({}, dry_run=False, shadow_mode=False)
    assert msg and "full_name" in msg
    assert truth_apply_live_blocked_message({}, dry_run=True, shadow_mode=False) is None
    assert truth_apply_live_blocked_message({}, dry_run=False, shadow_mode=True) is None


def test_truth_apply_hard_gate_enabled(monkeypatch):
    monkeypatch.delenv("TRUTH_APPLY_HARD_GATE", raising=False)
    assert truth_apply_hard_gate_enabled() is False
    monkeypatch.setenv("TRUTH_APPLY_HARD_GATE", "1")
    assert truth_apply_hard_gate_enabled() is True


def test_apply_to_jobs_payload_truth_gate_error(monkeypatch):
    monkeypatch.setenv("TRUTH_APPLY_HARD_GATE", "1")
    from services.linkedin_browser_automation import apply_to_jobs_payload

    with patch("services.profile_service.load_profile", return_value={}):
        out = apply_to_jobs_payload(
            [
                {
                    "title": "Eng",
                    "company": "Co",
                    "url": "https://www.linkedin.com/jobs/view/1",
                    "easy_apply_confirmed": True,
                }
            ],
            dry_run=False,
            shadow_mode=False,
            require_safeguards=False,
        )
    assert out.get("status") == "error"
    assert out.get("truth_gate") == "profile_incomplete"


def test_apply_to_jobs_payload_dry_run_bypasses_truth_gate(monkeypatch):
    monkeypatch.setenv("TRUTH_APPLY_HARD_GATE", "1")
    from services.linkedin_browser_automation import apply_to_jobs_payload

    with patch("services.profile_service.load_profile", return_value={}):
        out = apply_to_jobs_payload(
            [
                {
                    "title": "Eng",
                    "company": "Co",
                    "url": "https://www.linkedin.com/jobs/view/1",
                    "easy_apply_confirmed": True,
                }
            ],
            dry_run=True,
            shadow_mode=False,
            require_safeguards=False,
        )
    assert out.get("truth_gate") != "profile_incomplete"
