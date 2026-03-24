"""Unified follow-up digest notifier (multi-channel)."""

from unittest.mock import patch


def test_notify_dry_run(monkeypatch):
    monkeypatch.setenv("TRACKER_USE_DB", "0")
    import scripts.notify_follow_up_digest as nfd

    monkeypatch.setattr(
        nfd,
        "_load_env",
        lambda: None,
    )

    with patch("services.follow_up_service.list_follow_ups", return_value=[]):
        with patch("services.follow_up_service.format_follow_up_digest", return_value="DIGEST"):
            with patch("services.follow_up_webhook.follow_up_webhook_configured", return_value=True):
                with patch("services.follow_up_telegram.follow_up_telegram_configured", return_value=False):
                    with patch("services.follow_up_email.follow_up_smtp_configured", return_value=True):
                        import sys
                        from io import StringIO

                        old = sys.argv
                        try:
                            sys.argv = ["notify_follow_up_digest.py", "--dry-run"]
                            out = StringIO()
                            err = StringIO()
                            with patch.object(sys, "stdout", out):
                                with patch.object(sys, "stderr", err):
                                    code = nfd.main()
                        finally:
                            sys.argv = old
                        assert code == 0
                        assert "DIGEST" in out.getvalue()
                        assert "Webhook:  True" in out.getvalue()
                        assert "SMTP:     True" in out.getvalue()


def test_notify_no_items_exits_zero(monkeypatch):
    monkeypatch.setenv("TRACKER_USE_DB", "0")
    import scripts.notify_follow_up_digest as nfd

    monkeypatch.setattr(nfd, "_load_env", lambda: None)

    with patch("services.follow_up_service.list_follow_ups", return_value=[]):
        with patch("services.follow_up_service.format_follow_up_digest", return_value="x"):
            import sys

            old = sys.argv
            try:
                sys.argv = ["notify_follow_up_digest.py"]
                code = nfd.main()
            finally:
                sys.argv = old
            assert code == 0


def test_notify_no_channels_exit_2(monkeypatch):
    monkeypatch.setenv("TRACKER_USE_DB", "0")
    import scripts.notify_follow_up_digest as nfd

    monkeypatch.setattr(nfd, "_load_env", lambda: None)

    with patch("services.follow_up_service.list_follow_ups", return_value=[{"company": "A"}]):
        with patch("services.follow_up_service.format_follow_up_digest", return_value="body"):
            with patch("services.follow_up_webhook.follow_up_webhook_configured", return_value=False):
                with patch("services.follow_up_telegram.follow_up_telegram_configured", return_value=False):
                    with patch("services.follow_up_email.follow_up_smtp_configured", return_value=False):
                        import sys

                        old = sys.argv
                        try:
                            sys.argv = ["notify_follow_up_digest.py"]
                            code = nfd.main()
                        finally:
                            sys.argv = old
                        assert code == 2


def test_notify_partial_failure_exit_1(monkeypatch):
    monkeypatch.setenv("TRACKER_USE_DB", "0")
    import scripts.notify_follow_up_digest as nfd

    monkeypatch.setattr(nfd, "_load_env", lambda: None)

    with patch("services.follow_up_service.list_follow_ups", return_value=[{"company": "A"}]):
        with patch("services.follow_up_service.format_follow_up_digest", return_value="body"):
            with patch("services.follow_up_webhook.follow_up_webhook_configured", return_value=True):
                with patch("services.follow_up_telegram.follow_up_telegram_configured", return_value=True):
                    with patch("services.follow_up_email.follow_up_smtp_configured", return_value=False):
                        with patch(
                            "services.follow_up_webhook.send_follow_up_digest_webhook",
                            return_value=(False, "bad"),
                        ):
                            with patch(
                                "services.follow_up_telegram.send_follow_up_digest_telegram",
                                return_value=(True, "sent"),
                            ):
                                import sys

                                old = sys.argv
                                try:
                                    sys.argv = ["notify_follow_up_digest.py"]
                                    code = nfd.main()
                                finally:
                                    sys.argv = old
                                assert code == 1
