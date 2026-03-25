"""autonomy_submit_gate — Phase 3 LinkedIn live submit env gates."""

import pytest

from services.autonomy_submit_gate import linkedin_live_submit_block_reason


@pytest.fixture(autouse=True)
def _clear_autonomy_env(monkeypatch):
    monkeypatch.delenv("AUTONOMY_LINKEDIN_LIVE_SUBMIT_DISABLED", raising=False)
    monkeypatch.delenv("AUTONOMY_LINKEDIN_PILOT_SUBMIT_ONLY", raising=False)


def test_no_block_by_default():
    assert linkedin_live_submit_block_reason({}) is None


def test_kill_switch_blocks(monkeypatch):
    monkeypatch.setenv("AUTONOMY_LINKEDIN_LIVE_SUBMIT_DISABLED", "1")
    r = linkedin_live_submit_block_reason({"url": "https://linkedin.com/jobs/1"})
    assert r is not None
    assert "AUTONOMY_LINKEDIN_LIVE_SUBMIT_DISABLED" in r


def test_pilot_only_blocks_without_flag(monkeypatch):
    monkeypatch.setenv("AUTONOMY_LINKEDIN_PILOT_SUBMIT_ONLY", "true")
    assert linkedin_live_submit_block_reason({"url": "x"}) is not None
    assert linkedin_live_submit_block_reason({"pilot_submit_allowed": True}) is None
    assert linkedin_live_submit_block_reason({"pilot_submit": True}) is None


def test_kill_switch_wins_over_pilot(monkeypatch):
    monkeypatch.setenv("AUTONOMY_LINKEDIN_LIVE_SUBMIT_DISABLED", "yes")
    monkeypatch.setenv("AUTONOMY_LINKEDIN_PILOT_SUBMIT_ONLY", "1")
    r = linkedin_live_submit_block_reason({"pilot_submit_allowed": True})
    assert r is not None
    assert "LIVE_SUBMIT_DISABLED" in r
