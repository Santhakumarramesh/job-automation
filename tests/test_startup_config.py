"""Phase 3.5 — startup / secrets config collection."""

import os
from unittest.mock import patch


def test_production_requires_auth_credentials():
    from services.startup_checks import collect_startup_report

    with patch.dict(
        os.environ,
        {
            "APP_ENV": "production",
            "STRICT_STARTUP": "0",
            "API_KEY": "",
            "JWT_SECRET": "",
            "TRACKER_USE_DB": "1",
            "DATABASE_URL": "sqlite:///./job_applications.db",
        },
        clear=False,
    ):
        errors, _ = collect_startup_report("app")
    assert any("API_KEY" in e or "JWT_SECRET" in e for e in errors)


def test_demo_admin_forbidden_in_production():
    from services.startup_checks import collect_startup_report

    with patch.dict(
        os.environ,
        {
            "APP_ENV": "production",
            "STRICT_STARTUP": "0",
            "DEMO_USER_IS_ADMIN": "1",
            "API_KEY": "test-key-for-prod",
            "TRACKER_USE_DB": "1",
            "DATABASE_URL": "sqlite:///./job_applications.db",
        },
        clear=False,
    ):
        errors, _ = collect_startup_report("app")
    assert any("DEMO_USER_IS_ADMIN" in e for e in errors)


def test_worker_strict_requires_openai():
    from services.startup_checks import collect_startup_report

    with patch.dict(
        os.environ,
        {
            "STRICT_STARTUP": "1",
            "REDIS_BROKER": "redis://localhost:6379/0",
            "OPENAI_API_KEY": "",
        },
        clear=False,
    ):
        os.environ.pop("OPENAI_API_KEY", None)
        errors, _ = collect_startup_report("worker")
    assert any("OPENAI" in e.upper() or "openai" in e.lower() for e in errors)


def test_secrets_loader_skips_when_unconfigured():
    from services.secrets_loader import load_aws_secrets_manager_into_environ

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("AWS_SECRETS_MANAGER_SECRET_ID", None)
        assert load_aws_secrets_manager_into_environ() == []


def test_production_requires_tracker_db():
    from services.startup_checks import collect_startup_report

    with patch.dict(
        os.environ,
        {
            "APP_ENV": "production",
            "STRICT_STARTUP": "0",
            "API_KEY": "test-key",
            "JWT_SECRET": "x" * 32,
        },
        clear=False,
    ):
        os.environ.pop("TRACKER_USE_DB", None)
        os.environ.pop("DATABASE_URL", None)
        errors, _ = collect_startup_report("app")
    assert any("TRACKER_USE_DB" in e for e in errors)


def test_is_strict_respects_strict_startup_off():
    from services.startup_checks import is_strict_startup

    with patch.dict(
        os.environ,
        {"APP_ENV": "production", "STRICT_STARTUP": "0"},
        clear=False,
    ):
        assert is_strict_startup() is False
