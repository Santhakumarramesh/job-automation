"""Optional SMTP for follow-up digest."""

from unittest.mock import MagicMock, patch


def test_follow_up_smtp_configured(monkeypatch):
    from services import follow_up_email as fe

    monkeypatch.delenv("FOLLOW_UP_SMTP_HOST", raising=False)
    monkeypatch.delenv("FOLLOW_UP_EMAIL_TO", raising=False)
    assert fe.follow_up_smtp_configured() is False
    monkeypatch.setenv("FOLLOW_UP_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("FOLLOW_UP_EMAIL_TO", "me@example.com")
    assert fe.follow_up_smtp_configured() is True


def test_send_digest_missing_config(monkeypatch):
    from services.follow_up_email import send_follow_up_digest_email

    monkeypatch.delenv("FOLLOW_UP_SMTP_HOST", raising=False)
    monkeypatch.delenv("FOLLOW_UP_EMAIL_TO", raising=False)
    ok, msg = send_follow_up_digest_email("body")
    assert ok is False
    assert "FOLLOW_UP" in msg


def test_send_digest_calls_smtp(monkeypatch):
    from services.follow_up_email import send_follow_up_digest_email

    monkeypatch.setenv("FOLLOW_UP_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("FOLLOW_UP_SMTP_PORT", "587")
    monkeypatch.setenv("FOLLOW_UP_EMAIL_TO", "to@example.com")
    monkeypatch.setenv("FOLLOW_UP_SMTP_USER", "user")
    monkeypatch.setenv("FOLLOW_UP_SMTP_PASSWORD", "secret")

    mock_server = MagicMock()
    mock_server.__enter__ = MagicMock(return_value=mock_server)
    mock_server.__exit__ = MagicMock(return_value=None)

    with patch("services.follow_up_email.smtplib.SMTP", return_value=mock_server):
        ok, msg = send_follow_up_digest_email("Hello digest")
    assert ok is True
    assert msg == "sent"
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("user", "secret")
    mock_server.sendmail.assert_called_once()
