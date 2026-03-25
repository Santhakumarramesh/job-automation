"""Phase 4.3.3 — Redis metrics threshold webhook."""

import os
from unittest.mock import MagicMock, patch

import pytest


def test_run_no_thresholds_configured():
    from services.metrics_alert_webhook import run_metrics_webhook_alert

    with patch.dict(os.environ, {"CELERY_METRICS_REDIS": "1"}, clear=False):
        with patch(
            "services.metrics_redis.get_celery_metrics_summary",
            return_value={"enabled": True, "fields": {"tasks_error_total": "99"}},
        ):
            code, msg = run_metrics_webhook_alert(dry_run=True)
    assert code == 0
    assert "No METRICS_ALERT" in msg


def test_run_below_threshold():
    from services.metrics_alert_webhook import run_metrics_webhook_alert

    env = {"CELERY_METRICS_REDIS": "1", "METRICS_ALERT_ERROR_TOTAL_MIN": "100"}
    with patch.dict(os.environ, env, clear=False):
        with patch(
            "services.metrics_redis.get_celery_metrics_summary",
            return_value={"enabled": True, "fields": {"tasks_error_total": "5"}},
        ):
            code, msg = run_metrics_webhook_alert(dry_run=True)
    assert code == 0
    assert "below" in msg.lower()


def test_run_dry_run_when_threshold_hit():
    from services.metrics_alert_webhook import run_metrics_webhook_alert

    env = {"CELERY_METRICS_REDIS": "1", "METRICS_ALERT_ERROR_TOTAL_MIN": "1"}
    with patch.dict(os.environ, env, clear=False):
        with patch(
            "services.metrics_redis.get_celery_metrics_summary",
            return_value={"enabled": True, "fields": {"tasks_error_total": "3"}},
        ):
            code, msg = run_metrics_webhook_alert(dry_run=True)
    assert code == 0
    assert "dry-run" in msg.lower()
    assert "tasks_error_total" in msg


def test_post_success_writes_cooldown(tmp_path, monkeypatch):
    from services import metrics_alert_webhook as maw

    monkeypatch.setattr(maw, "_COOLDOWN_FILE", tmp_path / "last")
    env = {
        "CELERY_METRICS_REDIS": "1",
        "METRICS_ALERT_ERROR_TOTAL_MIN": "1",
        "METRICS_ALERT_WEBHOOK_URL": "https://example.com/hook",
        "METRICS_ALERT_COOLDOWN_SECONDS": "0",
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 204
    mock_resp.text = ""

    with patch.dict(os.environ, env, clear=False):
        with patch(
            "services.metrics_redis.get_celery_metrics_summary",
            return_value={"enabled": True, "fields": {"tasks_error_total": "2"}},
        ):
            with patch("requests.post", return_value=mock_resp) as post:
                code, msg = maw.run_metrics_webhook_alert(dry_run=False)
    assert code == 0
    assert post.called
    assert (tmp_path / "last").is_file()
