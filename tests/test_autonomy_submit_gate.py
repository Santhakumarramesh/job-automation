"""autonomy_submit_gate — Phase 3 LinkedIn live submit env gates."""

import pytest

from services.autonomy_submit_gate import linkedin_live_submit_block_reason


@pytest.fixture(autouse=True)
def _clear_autonomy_env(monkeypatch):
    monkeypatch.delenv("AUTONOMY_LINKEDIN_LIVE_SUBMIT_DISABLED", raising=False)
    monkeypatch.delenv("AUTONOMY_LINKEDIN_PILOT_SUBMIT_ONLY", raising=False)
    monkeypatch.delenv("AUTONOMY_LINKEDIN_PILOT_USER_IDS", raising=False)
    monkeypatch.delenv("AUTONOMY_LINKEDIN_PILOT_WORKSPACE_IDS", raising=False)
    monkeypatch.delenv("AUTONOMY_LINKEDIN_ROLLBACK_WHEN_FAILURE_RATE_GTE", raising=False)
    monkeypatch.delenv("AUTONOMY_LINKEDIN_ROLLBACK_MIN_ATTEMPTS", raising=False)
    monkeypatch.delenv("AUTONOMY_LINKEDIN_ROLLBACK_WHEN_NONSUBMIT_RATE_GTE", raising=False)
    monkeypatch.delenv("AUTONOMY_LINKEDIN_ROLLBACK_NONSUBMIT_MIN_EVENTS", raising=False)


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


def test_pilot_user_allowlist(monkeypatch):
    monkeypatch.setenv("AUTONOMY_LINKEDIN_PILOT_SUBMIT_ONLY", "1")
    monkeypatch.setenv("AUTONOMY_LINKEDIN_PILOT_USER_IDS", "u1, u2")
    assert linkedin_live_submit_block_reason({"url": "x"}) is not None
    assert linkedin_live_submit_block_reason({"user_id": "u1"}) is None
    assert linkedin_live_submit_block_reason({"authenticated_user_id": "u2"}) is None


def test_pilot_workspace_allowlist(monkeypatch):
    monkeypatch.setenv("AUTONOMY_LINKEDIN_PILOT_SUBMIT_ONLY", "1")
    monkeypatch.setenv("AUTONOMY_LINKEDIN_PILOT_WORKSPACE_IDS", "ws-a")
    assert linkedin_live_submit_block_reason({}) is not None
    assert linkedin_live_submit_block_reason({"workspace_id": "ws-a"}) is None
    assert linkedin_live_submit_block_reason({"organization_id": "ws-a"}) is None


def test_empty_allowlists_fall_back_to_job_flag_only(monkeypatch):
    monkeypatch.setenv("AUTONOMY_LINKEDIN_PILOT_SUBMIT_ONLY", "1")
    monkeypatch.setenv("AUTONOMY_LINKEDIN_PILOT_USER_IDS", "")
    monkeypatch.setenv("AUTONOMY_LINKEDIN_PILOT_WORKSPACE_IDS", "  ,  ")
    assert linkedin_live_submit_block_reason({"user_id": "any"}) is not None
    assert linkedin_live_submit_block_reason({"pilot_submit_allowed": True}) is None


def test_telemetry_rollback_blocks_when_failure_rate_high(monkeypatch):
    monkeypatch.setenv("AUTONOMY_LINKEDIN_ROLLBACK_WHEN_FAILURE_RATE_GTE", "0.5")
    monkeypatch.setenv("AUTONOMY_LINKEDIN_ROLLBACK_MIN_ATTEMPTS", "4")

    def _totals():
        return (10, 4)

    monkeypatch.setattr(
        "services.apply_runner_metrics_redis.read_linkedin_live_submit_totals",
        _totals,
    )
    r = linkedin_live_submit_block_reason({})
    assert r is not None
    assert "telemetry rollback" in r


def test_telemetry_rollback_skips_below_min_attempts(monkeypatch):
    monkeypatch.setenv("AUTONOMY_LINKEDIN_ROLLBACK_WHEN_FAILURE_RATE_GTE", "0.1")
    monkeypatch.setenv("AUTONOMY_LINKEDIN_ROLLBACK_MIN_ATTEMPTS", "100")

    def _totals():
        return (5, 0)

    monkeypatch.setattr(
        "services.apply_runner_metrics_redis.read_linkedin_live_submit_totals",
        _totals,
    )
    assert linkedin_live_submit_block_reason({}) is None


def test_pattern_rollback_blocks_when_nonsubmit_rate_high(monkeypatch):
    monkeypatch.setenv("AUTONOMY_LINKEDIN_ROLLBACK_WHEN_NONSUBMIT_RATE_GTE", "0.5")
    monkeypatch.setenv("AUTONOMY_LINKEDIN_ROLLBACK_NONSUBMIT_MIN_EVENTS", "4")

    def _pair():
        return (5, 8)

    monkeypatch.setattr(
        "services.apply_runner_metrics_redis.read_linkedin_nonsubmit_pattern_totals",
        _pair,
    )
    r = linkedin_live_submit_block_reason({})
    assert r is not None
    assert "pattern rollback" in r


def test_pattern_rollback_skips_below_min_events(monkeypatch):
    monkeypatch.setenv("AUTONOMY_LINKEDIN_ROLLBACK_WHEN_NONSUBMIT_RATE_GTE", "0.01")
    monkeypatch.setenv("AUTONOMY_LINKEDIN_ROLLBACK_NONSUBMIT_MIN_EVENTS", "100")

    def _pair():
        return (99, 99)

    monkeypatch.setattr(
        "services.apply_runner_metrics_redis.read_linkedin_nonsubmit_pattern_totals",
        _pair,
    )
    assert linkedin_live_submit_block_reason({}) is None


def test_submit_failure_rollback_wins_over_pattern_rollback(monkeypatch):
    monkeypatch.setenv("AUTONOMY_LINKEDIN_ROLLBACK_WHEN_FAILURE_RATE_GTE", "0.5")
    monkeypatch.setenv("AUTONOMY_LINKEDIN_ROLLBACK_MIN_ATTEMPTS", "2")
    monkeypatch.setenv("AUTONOMY_LINKEDIN_ROLLBACK_WHEN_NONSUBMIT_RATE_GTE", "0.5")
    monkeypatch.setenv("AUTONOMY_LINKEDIN_ROLLBACK_NONSUBMIT_MIN_EVENTS", "2")

    monkeypatch.setattr(
        "services.apply_runner_metrics_redis.read_linkedin_live_submit_totals",
        lambda: (10, 4),
    )
    monkeypatch.setattr(
        "services.apply_runner_metrics_redis.read_linkedin_nonsubmit_pattern_totals",
        lambda: (10, 10),
    )
    r = linkedin_live_submit_block_reason({})
    assert r is not None
    assert "telemetry rollback" in r
    assert "pattern rollback" not in r


def test_kill_switch_wins_over_telemetry_rollback(monkeypatch):
    monkeypatch.setenv("AUTONOMY_LINKEDIN_LIVE_SUBMIT_DISABLED", "1")
    monkeypatch.setenv("AUTONOMY_LINKEDIN_ROLLBACK_WHEN_FAILURE_RATE_GTE", "0.01")
    monkeypatch.setattr(
        "services.apply_runner_metrics_redis.read_linkedin_live_submit_totals",
        lambda: (999, 0),
    )
    r = linkedin_live_submit_block_reason({})
    assert r is not None
    assert "LIVE_SUBMIT_DISABLED" in r
