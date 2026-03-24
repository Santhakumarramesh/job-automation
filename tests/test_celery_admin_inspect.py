"""Phase 4.2.3 — Celery inspect helper."""

from unittest.mock import MagicMock, patch


def test_celery_inspect_snapshot_ok():
    mock_insp = MagicMock()
    mock_insp.ping.return_value = {"celery@host": {"ok": "pong"}}
    mock_insp.active.return_value = {}
    mock_insp.reserved.return_value = {}
    mock_insp.scheduled.return_value = {}
    mock_insp.stats.return_value = {}

    mock_celery = MagicMock()
    mock_celery.control.inspect.return_value = mock_insp

    with patch("app.tasks.celery", mock_celery):
        from services.celery_admin_inspect import celery_inspect_snapshot

        out = celery_inspect_snapshot(timeout_sec=1.0)

    assert out["ok"] is True
    assert out["workers"]["ping"] == {"celery@host": {"ok": "pong"}}
    mock_celery.control.inspect.assert_called_once_with(timeout=1.0)


def test_celery_inspect_snapshot_when_inspect_none():
    mock_celery = MagicMock()
    mock_celery.control.inspect.return_value = None

    with patch("app.tasks.celery", mock_celery):
        from services.celery_admin_inspect import celery_inspect_snapshot

        out = celery_inspect_snapshot(timeout_sec=1.0)

    assert out["ok"] is False
    assert "error" in out
