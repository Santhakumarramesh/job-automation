"""Phase 3.6 — Redis-backed Celery metrics."""

import os
from unittest.mock import MagicMock, patch


def test_incr_noop_when_disabled():
    from services.metrics_redis import incr_celery_task

    with patch.dict(os.environ, {"CELERY_METRICS_REDIS": "0"}, clear=False):
        incr_celery_task(outcome="success", duration_seconds=1.0)


def test_get_summary_reports_disabled():
    from services.metrics_redis import get_celery_metrics_summary

    with patch.dict(os.environ, {"CELERY_METRICS_REDIS": "0"}, clear=False):
        s = get_celery_metrics_summary()
    assert s.get("enabled") is False


def test_incr_calls_redis_pipeline():
    from services import metrics_redis as mr

    mock_r = MagicMock()
    mock_pipe = MagicMock()
    mock_r.pipeline.return_value = mock_pipe

    with patch.dict(
        os.environ,
        {"CELERY_METRICS_REDIS": "1", "REDIS_BROKER": "redis://localhost:6379/0"},
        clear=False,
    ):
        with patch.object(mr, "_client", return_value=mock_r):
            mr.incr_celery_task(outcome="success", failure_class="", duration_seconds=2.5)

    mock_r.pipeline.assert_called_once()
    mock_pipe.hincrby.assert_called()
    mock_pipe.hincrbyfloat.assert_called()
    mock_pipe.execute.assert_called_once()


def test_read_celery_metrics_hash_requires_url():
    from services.metrics_redis import read_celery_metrics_hash

    with patch.dict(os.environ, {}, clear=True):
        out = read_celery_metrics_hash()
    assert out["ok"] is False


def test_apply_runner_incr_noop_when_disabled():
    from services.apply_runner_metrics_redis import incr_apply_runner_event

    with patch.dict(os.environ, {"APPLY_RUNNER_METRICS_REDIS": "0"}, clear=False):
        incr_apply_runner_event("linkedin_login_challenge_abort")


def test_apply_runner_incr_ignores_unknown_event():
    from services import apply_runner_metrics_redis as ar

    mock_r = MagicMock()
    mock_pipe = MagicMock()
    mock_r.pipeline.return_value = mock_pipe

    with patch.dict(
        os.environ,
        {"APPLY_RUNNER_METRICS_REDIS": "1", "REDIS_BROKER": "redis://localhost:6379/0"},
        clear=False,
    ):
        with patch.object(ar, "_client", return_value=mock_r):
            ar.incr_apply_runner_event("not_a_real_event")
    mock_r.pipeline.assert_not_called()


def test_read_linkedin_nonsubmit_pattern_totals():
    from services import apply_runner_metrics_redis as ar

    mock_r = MagicMock()
    mock_r.hgetall.return_value = {
        "linkedin_login_checkpoint_pause_total": "3",
        "linkedin_login_challenge_abort_total": "2",
        "linkedin_live_submit_attempt_total": "5",
    }
    with patch.dict(os.environ, {"REDIS_BROKER": "redis://localhost:6379/0"}, clear=False):
        with patch.object(ar, "_client", return_value=mock_r):
            assert ar.read_linkedin_nonsubmit_pattern_totals() == (5, 10)

    with patch.dict(os.environ, {}, clear=True):
        with patch.object(ar, "_client", return_value=None):
            assert ar.read_linkedin_nonsubmit_pattern_totals() is None


def test_read_linkedin_live_submit_totals():
    from services import apply_runner_metrics_redis as ar

    mock_r = MagicMock()
    mock_r.hgetall.return_value = {
        "linkedin_live_submit_attempt_total": "8",
        "linkedin_live_submit_success_total": "99",
    }
    with patch.dict(os.environ, {"REDIS_BROKER": "redis://localhost:6379/0"}, clear=False):
        with patch.object(ar, "_client", return_value=mock_r):
            assert ar.read_linkedin_live_submit_totals() == (8, 8)

    with patch.dict(os.environ, {}, clear=True):
        with patch.object(ar, "_client", return_value=None):
            assert ar.read_linkedin_live_submit_totals() is None


def test_apply_runner_incr_calls_redis():
    from services import apply_runner_metrics_redis as ar

    mock_r = MagicMock()
    mock_pipe = MagicMock()
    mock_r.pipeline.return_value = mock_pipe

    with patch.dict(
        os.environ,
        {"APPLY_RUNNER_METRICS_REDIS": "1", "REDIS_BROKER": "redis://localhost:6379/0"},
        clear=False,
    ):
        with patch.object(ar, "_client", return_value=mock_r):
            ar.incr_apply_runner_event("linkedin_login_checkpoint_pause")

    mock_pipe.hincrby.assert_called()
    mock_pipe.execute.assert_called_once()


def test_apply_runner_duration_incr_noop_when_disabled():
    from services.apply_runner_metrics_redis import incr_apply_runner_duration

    with patch.dict(os.environ, {"APPLY_RUNNER_METRICS_REDIS": "0"}, clear=False):
        incr_apply_runner_duration("linkedin_fill_total", 1.0)


def test_apply_runner_duration_incr_ignores_unknown_stage():
    from services import apply_runner_metrics_redis as ar

    mock_r = MagicMock()
    mock_pipe = MagicMock()
    mock_r.pipeline.return_value = mock_pipe

    with patch.dict(
        os.environ,
        {"APPLY_RUNNER_METRICS_REDIS": "1", "REDIS_BROKER": "redis://localhost:6379/0"},
        clear=False,
    ):
        with patch.object(ar, "_client", return_value=mock_r):
            ar.incr_apply_runner_duration("not_a_real_stage", 1.23)

    mock_r.pipeline.assert_not_called()


def test_apply_runner_duration_incr_calls_redis():
    from services import apply_runner_metrics_redis as ar

    mock_r = MagicMock()
    mock_pipe = MagicMock()
    mock_r.pipeline.return_value = mock_pipe

    with patch.dict(
        os.environ,
        {"APPLY_RUNNER_METRICS_REDIS": "1", "REDIS_BROKER": "redis://localhost:6379/0"},
        clear=False,
    ):
        with patch.object(ar, "_client", return_value=mock_r):
            ar.incr_apply_runner_duration("linkedin_fill_dom_scan", 2.5)

    mock_pipe.hincrbyfloat.assert_called()
    mock_pipe.hincrby.assert_called()
    mock_pipe.execute.assert_called_once()


def test_celery_summary_merges_apply_runner_fields():
    from services import metrics_redis as mr

    mock_r = MagicMock()
    mock_r.hgetall.return_value = {"tasks_total": "1"}

    def fake_read():
        return {
            "enabled": True,
            "hash": "ccp:metrics:apply_runner",
            "fields": {"linkedin_login_challenge_abort_total": "2"},
        }

    with patch.dict(
        os.environ,
        {"CELERY_METRICS_REDIS": "1", "REDIS_BROKER": "redis://localhost:6379/0"},
        clear=False,
    ):
        with patch.object(mr, "_client", return_value=mock_r):
            with patch(
                "services.apply_runner_metrics_redis.read_apply_runner_metrics_summary",
                fake_read,
            ):
                s = mr.get_celery_metrics_summary()

    assert s.get("enabled") is True
    assert s.get("apply_runner", {}).get("fields", {}).get("linkedin_login_challenge_abort_total") == "2"


def test_path_group_limits_cardinality():
    from services.prometheus_setup import _path_group

    assert _path_group("/api/jobs/uuid-here") == "/api/jobs"
    assert _path_group("/api/v1/jobs/uuid-here") == "/api/v1"
    assert _path_group("/api/admin/metrics/summary") == "/api/admin"
    assert _path_group("/health") == "/health"
    assert _path_group("/") == "/"
