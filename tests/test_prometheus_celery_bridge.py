"""Phase 4.3 — expose Redis Celery counters on Prometheus scrape."""

import os
from unittest.mock import patch

import pytest

pytest.importorskip("prometheus_client")


def test_prometheus_celery_bridge_refresh_sets_gauges():
    from prometheus_client import CollectorRegistry, generate_latest

    import services.prometheus_celery_bridge as pcb

    pcb.reset_celery_bridge_state_for_tests()
    reg = CollectorRegistry()
    with patch.dict(os.environ, {"PROMETHEUS_CELERY_REDIS": "1"}, clear=False):
        assert pcb.register_celery_redis_gauges(reg) is True
    fake_fields = {
        "tasks_total": "10",
        "tasks_success_total": "7",
        "tasks_rejected_total": "1",
        "tasks_error_total": "2",
        "tasks_error_transient": "1",
        "tasks_error_permanent": "1",
        "task_duration_seconds_sum": "45.5",
        "task_duration_count": "10",
    }
    with patch("services.metrics_redis.read_celery_metrics_hash", return_value={"ok": True, "fields": fake_fields}):
        pcb.refresh_celery_redis_gauges()
    body = generate_latest(reg).decode()
    assert "ccp_celery_tasks_total 10.0" in body
    assert "ccp_celery_tasks_success_total 7.0" in body
    assert "ccp_celery_task_duration_seconds_sum 45.5" in body
    pcb.reset_celery_bridge_state_for_tests()


def test_bridge_disabled_when_env_off():
    import services.prometheus_celery_bridge as pcb

    pcb.reset_celery_bridge_state_for_tests()
    from prometheus_client import CollectorRegistry

    reg = CollectorRegistry()
    with patch.dict(
        os.environ,
        {"PROMETHEUS_CELERY_REDIS": "0", "CELERY_METRICS_REDIS": "1"},
        clear=False,
    ):
        assert pcb.register_celery_redis_gauges(reg) is False
    pcb.reset_celery_bridge_state_for_tests()


def test_refresh_zeroes_on_redis_failure():
    from prometheus_client import CollectorRegistry, generate_latest

    import services.prometheus_celery_bridge as pcb

    pcb.reset_celery_bridge_state_for_tests()
    reg = CollectorRegistry()
    with patch.dict(os.environ, {"PROMETHEUS_CELERY_REDIS": "1"}, clear=False):
        assert pcb.register_celery_redis_gauges(reg) is True
    with patch(
        "services.metrics_redis.read_celery_metrics_hash",
        return_value={"ok": False, "reason": "down", "fields": {}},
    ):
        pcb.refresh_celery_redis_gauges()
    body = generate_latest(reg).decode()
    assert "ccp_celery_tasks_total 0.0" in body
    pcb.reset_celery_bridge_state_for_tests()
