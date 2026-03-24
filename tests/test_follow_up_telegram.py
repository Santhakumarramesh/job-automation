"""Optional Telegram Bot API for follow-up digest."""

from unittest.mock import MagicMock, patch


def test_follow_up_telegram_configured(monkeypatch):
    from services import follow_up_telegram as ft

    monkeypatch.delenv("FOLLOW_UP_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("FOLLOW_UP_TELEGRAM_CHAT_ID", raising=False)
    assert ft.follow_up_telegram_configured() is False
    monkeypatch.setenv("FOLLOW_UP_TELEGRAM_BOT_TOKEN", "123:ABC")
    monkeypatch.setenv("FOLLOW_UP_TELEGRAM_CHAT_ID", "999")
    assert ft.follow_up_telegram_configured() is True


def test_send_missing_config(monkeypatch):
    from services.follow_up_telegram import send_follow_up_digest_telegram

    monkeypatch.delenv("FOLLOW_UP_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("FOLLOW_UP_TELEGRAM_CHAT_ID", raising=False)
    ok, msg = send_follow_up_digest_telegram("x")
    assert ok is False
    assert "TELEGRAM" in msg


def test_send_calls_api(monkeypatch):
    from services.follow_up_telegram import send_follow_up_digest_telegram

    monkeypatch.setenv("FOLLOW_UP_TELEGRAM_BOT_TOKEN", "T")
    monkeypatch.setenv("FOLLOW_UP_TELEGRAM_CHAT_ID", "42")

    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"ok": True, "result": {"message_id": 1}}
    mock_resp.text = '{"ok":true}'

    with patch("services.follow_up_telegram.requests.post", return_value=mock_resp) as post:
        ok, msg = send_follow_up_digest_telegram("Hello")
    assert ok is True
    assert msg == "sent"
    post.assert_called_once()
    assert "botT/sendMessage" in post.call_args[0][0]
    assert post.call_args.kwargs["json"]["chat_id"] == "42"
    assert post.call_args.kwargs["json"]["text"] == "Hello"


def test_send_api_error(monkeypatch):
    from services.follow_up_telegram import send_follow_up_digest_telegram

    monkeypatch.setenv("FOLLOW_UP_TELEGRAM_BOT_TOKEN", "T")
    monkeypatch.setenv("FOLLOW_UP_TELEGRAM_CHAT_ID", "42")

    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 400
    mock_resp.text = '{"ok":false,"description":"bad chat"}'
    mock_resp.json.return_value = {"ok": False, "description": "bad chat"}

    with patch("services.follow_up_telegram.requests.post", return_value=mock_resp):
        ok, msg = send_follow_up_digest_telegram("x")
    assert ok is False
    assert "bad chat" in msg
