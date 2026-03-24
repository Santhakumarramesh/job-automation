"""Optional webhook POST for follow-up digest."""

from unittest.mock import MagicMock, patch


def test_follow_up_webhook_configured(monkeypatch):
    from services import follow_up_webhook as fw

    monkeypatch.delenv("FOLLOW_UP_WEBHOOK_URL", raising=False)
    assert fw.follow_up_webhook_configured() is False
    monkeypatch.setenv("FOLLOW_UP_WEBHOOK_URL", "https://hooks.slack.com/services/x")
    assert fw.follow_up_webhook_configured() is True


def test_send_digest_missing_url(monkeypatch):
    from services.follow_up_webhook import send_follow_up_digest_webhook

    monkeypatch.delenv("FOLLOW_UP_WEBHOOK_URL", raising=False)
    ok, msg = send_follow_up_digest_webhook("body")
    assert ok is False
    assert "FOLLOW_UP_WEBHOOK_URL" in msg


def test_send_slack_style(monkeypatch):
    from services.follow_up_webhook import send_follow_up_digest_webhook

    monkeypatch.setenv("FOLLOW_UP_WEBHOOK_URL", "https://hooks.slack.com/test")
    monkeypatch.setenv("FOLLOW_UP_WEBHOOK_STYLE", "slack")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "ok"

    with patch("services.follow_up_webhook.requests.post", return_value=mock_resp) as post:
        ok, msg = send_follow_up_digest_webhook("Hello")
    assert ok is True
    assert "200" in msg
    post.assert_called_once()
    call_kw = post.call_args.kwargs
    assert call_kw["json"] == {"text": "Hello"}


def test_send_discord_style(monkeypatch):
    from services.follow_up_webhook import send_follow_up_digest_webhook

    monkeypatch.setenv("FOLLOW_UP_WEBHOOK_URL", "https://discord.com/api/webhooks/x")
    monkeypatch.setenv("FOLLOW_UP_WEBHOOK_STYLE", "discord")

    mock_resp = MagicMock()
    mock_resp.status_code = 204
    mock_resp.text = ""

    with patch("services.follow_up_webhook.requests.post", return_value=mock_resp) as post:
        ok, msg = send_follow_up_digest_webhook("Hi")
    assert ok is True
    assert post.call_args.kwargs["json"] == {"content": "Hi"}


def test_send_raw_style(monkeypatch):
    from services.follow_up_webhook import send_follow_up_digest_webhook

    monkeypatch.setenv("FOLLOW_UP_WEBHOOK_URL", "https://example.com/notify")
    monkeypatch.setenv("FOLLOW_UP_WEBHOOK_STYLE", "raw")

    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.text = ""

    with patch("services.follow_up_webhook.requests.post", return_value=mock_resp) as post:
        ok, msg = send_follow_up_digest_webhook("plain")
    assert ok is True
    assert post.call_args.kwargs["data"] == b"plain"
    assert "text/plain" in post.call_args.kwargs["headers"]["Content-Type"]
