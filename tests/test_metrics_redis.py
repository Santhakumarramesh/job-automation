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


def test_path_group_limits_cardinality():
    from services.prometheus_setup import _path_group

    assert _path_group("/api/jobs/uuid-here") == "/api/jobs"
    assert _path_group("/api/admin/metrics/summary") == "/api/admin"
    assert _path_group("/health") == "/health"
    assert _path_group("/") == "/"
