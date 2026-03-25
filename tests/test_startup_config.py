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
            "JWT_JWKS_URL": "",
            "JWT_ISSUER": "",
            "M2M_API_KEY": "",
            "TRACKER_USE_DB": "1",
            "DATABASE_URL": "sqlite:///./job_applications.db",
        },
        clear=False,
    ):
        errors, _ = collect_startup_report("app")
    assert any("demo-user" in e and ("API_KEY" in e or "JWT" in e or "M2M" in e) for e in errors)


def test_production_jwks_url_satisfies_auth_gate():
    from services.startup_checks import collect_startup_report

    with patch.dict(
        os.environ,
        {
            "APP_ENV": "production",
            "STRICT_STARTUP": "0",
            "API_KEY": "",
            "JWT_SECRET": "",
            "JWT_JWKS_URL": "https://issuer.example.com/.well-known/jwks.json",
            "TRACKER_USE_DB": "1",
            "DATABASE_URL": "sqlite:///./job_applications.db",
        },
        clear=False,
    ):
        errors, _ = collect_startup_report("app")
    assert not any("demo-user" in e for e in errors)


def test_production_m2m_only_satisfies_auth_gate():
    from services.startup_checks import collect_startup_report

    with patch.dict(
        os.environ,
        {
            "APP_ENV": "production",
            "STRICT_STARTUP": "0",
            "API_KEY": "",
            "JWT_SECRET": "",
            "JWT_JWKS_URL": "",
            "JWT_ISSUER": "",
            "M2M_API_KEY": "machine-to-machine-secret-key-12345",
            "TRACKER_USE_DB": "1",
            "DATABASE_URL": "sqlite:///./job_applications.db",
        },
        clear=False,
    ):
        errors, _ = collect_startup_report("app")
    assert not any("demo-user" in e for e in errors)


def test_production_warns_when_jwks_without_audience():
    from services.startup_checks import collect_startup_report

    with patch.dict(
        os.environ,
        {
            "APP_ENV": "production",
            "STRICT_STARTUP": "0",
            "API_KEY": "k",
            "JWT_JWKS_URL": "https://issuer.example.com/jwks",
            "TRACKER_USE_DB": "1",
            "DATABASE_URL": "sqlite:///./job_applications.db",
        },
        clear=False,
    ):
        os.environ.pop("JWT_AUDIENCE", None)
        _, warnings = collect_startup_report("app")
    assert any("JWT_AUDIENCE" in w for w in warnings)


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


def test_production_warns_when_rate_limit_disabled():
    from services.startup_checks import collect_startup_report

    with patch.dict(
        os.environ,
        {
            "APP_ENV": "production",
            "STRICT_STARTUP": "0",
            "API_KEY": "k",
            "JWT_SECRET": "x" * 32,
            "TRACKER_USE_DB": "1",
            "DATABASE_URL": "sqlite:///./job_applications.db",
        },
        clear=False,
    ):
        os.environ.pop("API_RATE_LIMIT_ENABLED", None)
        os.environ.pop("API_RATE_LIMIT_SKIP_STARTUP_WARN", None)
        _, warnings = collect_startup_report("app")
    assert any("API_RATE_LIMIT_ENABLED is not set" in w for w in warnings)


def test_production_rate_limit_warning_suppressed():
    from services.startup_checks import collect_startup_report

    with patch.dict(
        os.environ,
        {
            "APP_ENV": "production",
            "STRICT_STARTUP": "0",
            "API_KEY": "k",
            "JWT_SECRET": "x" * 32,
            "TRACKER_USE_DB": "1",
            "DATABASE_URL": "sqlite:///./job_applications.db",
            "API_RATE_LIMIT_SKIP_STARTUP_WARN": "1",
        },
        clear=False,
    ):
        os.environ.pop("API_RATE_LIMIT_ENABLED", None)
        _, warnings = collect_startup_report("app")
    assert not any("API_RATE_LIMIT_ENABLED is not set" in w for w in warnings)


def test_development_does_not_warn_rate_limit():
    from services.startup_checks import collect_startup_report

    with patch.dict(
        os.environ,
        {"APP_ENV": "development"},
        clear=False,
    ):
        _, warnings = collect_startup_report("app")
    assert not any("API_RATE_LIMIT_ENABLED is not set" in w for w in warnings)


def test_production_rejects_cors_wildcard():
    from services.startup_checks import collect_startup_report

    with patch.dict(
        os.environ,
        {
            "APP_ENV": "production",
            "STRICT_STARTUP": "0",
            "API_KEY": "k",
            "JWT_SECRET": "x" * 32,
            "TRACKER_USE_DB": "1",
            "DATABASE_URL": "sqlite:///./job_applications.db",
            "API_CORS_ORIGINS": "*",
        },
        clear=False,
    ):
        os.environ.pop("API_CORS_SKIP_WILDCARD_PROD_CHECK", None)
        errors, _ = collect_startup_report("app")
    assert any("API_CORS_ORIGINS" in e and "*" in e for e in errors)


def test_production_cors_wildcard_allowed_with_skip_flag():
    from services.startup_checks import collect_startup_report

    with patch.dict(
        os.environ,
        {
            "APP_ENV": "production",
            "STRICT_STARTUP": "0",
            "API_KEY": "k",
            "JWT_SECRET": "x" * 32,
            "TRACKER_USE_DB": "1",
            "DATABASE_URL": "sqlite:///./job_applications.db",
            "API_CORS_ORIGINS": "*",
            "API_CORS_SKIP_WILDCARD_PROD_CHECK": "1",
        },
        clear=False,
    ):
        errors, _ = collect_startup_report("app")
    assert not any("API_CORS_ORIGINS" in e for e in errors)


def test_strict_nonprod_warns_cors_wildcard():
    from services.startup_checks import collect_startup_report

    with patch.dict(
        os.environ,
        {
            "APP_ENV": "development",
            "STRICT_STARTUP": "1",
            "API_CORS_ORIGINS": "*",
        },
        clear=False,
    ):
        os.environ.pop("API_CORS_SKIP_WILDCARD_PROD_CHECK", None)
        _, warnings = collect_startup_report("app")
    assert any("API_CORS_ORIGINS" in w for w in warnings)
