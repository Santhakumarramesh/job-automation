"""
Startup validation — env separation & production guardrails (Phase 3.5).

- Loads optional AWS Secrets Manager JSON into the environment first.
- ``APP_ENV=production`` (or ``ENV=production``) enables **strict** fatal checks
  unless ``STRICT_STARTUP=0`` is set.
- ``STRICT_STARTUP=1`` forces strict checks in any environment.

Strict mode calls ``sys.exit(1)`` when **errors** are present (after printing them).
Warnings are always printed and never exit.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Tuple


def is_production_environment() -> bool:
    e = (os.getenv("APP_ENV") or os.getenv("ENV") or "").strip().lower()
    return e in ("production", "prod")


def is_strict_startup() -> bool:
    if (os.getenv("STRICT_STARTUP") or "").strip().lower() in ("0", "false", "no"):
        return False
    if (os.getenv("STRICT_STARTUP") or "").strip().lower() in ("1", "true", "yes"):
        return True
    return is_production_environment()


def collect_startup_report(context: str = "app") -> Tuple[List[str], List[str]]:
    """
    Returns (errors, warnings). Errors are fatal when strict startup is enabled.
    """
    errors: List[str] = []
    warnings: List[str] = []
    strict = is_strict_startup()
    prod = is_production_environment()

    # --- Optional AWS Secrets (strict: failure to load is an error) ---
    secret_id = (os.getenv("AWS_SECRETS_MANAGER_SECRET_ID") or "").strip()
    if secret_id:
        try:
            from services.secrets_loader import load_aws_secrets_manager_into_environ

            applied = load_aws_secrets_manager_into_environ()
            if applied:
                print(f"✅ Startup: applied {len(applied)} key(s) from AWS Secrets Manager (existing env preserved).")
        except Exception as e:
            msg = f"AWS Secrets Manager: {e}"
            if strict:
                errors.append(msg)
            else:
                warnings.append(msg)

    api_key = (os.getenv("API_KEY") or "").strip()
    jwt_secret = (os.getenv("JWT_SECRET") or "").strip()

    if context == "app":
        if not api_key and not jwt_secret:
            msg = "API_KEY and JWT_SECRET are both unset — API is open (demo-user only)."
            if strict or prod:
                errors.append(msg)
            else:
                warnings.append(msg)
        elif not api_key and jwt_secret:
            warnings.append("API_KEY not set — clients must use JWT (Authorization: Bearer).")

    if prod and (os.getenv("DEMO_USER_IS_ADMIN") or "").lower() in ("1", "true", "yes"):
        errors.append("DEMO_USER_IS_ADMIN must not be enabled in production (APP_ENV=production).")

    if prod and jwt_secret and len(jwt_secret) < 32:
        warnings.append("JWT_SECRET is shorter than 32 chars — use a long random secret in production.")

    if context in ("streamlit", "app", "worker"):
        key = os.getenv("OPENAI_API_KEY", "").strip()
        if not key or len(key) < 20:
            msg = "OPENAI_API_KEY missing or invalid — ATS/LLM features may fail"
            if strict and context == "worker":
                errors.append(msg)
            else:
                warnings.append(msg)

    if context == "worker":
        broker = (os.getenv("REDIS_BROKER") or "").strip()
        if not broker:
            errors.append("REDIS_BROKER is required for Celery workers.")
        elif prod and "localhost" in broker.lower() and "redis" in broker.lower():
            warnings.append("REDIS_BROKER points at localhost in production — use a managed Redis URL.")

    if context in ("app", "worker") and prod:
        backend = (os.getenv("REDIS_BACKEND") or "").strip()
        if backend and "localhost" in backend.lower():
            warnings.append("REDIS_BACKEND points at localhost in production — confirm this is intentional.")

    if os.getenv("TRACKER_USE_DB", "").lower() in ("1", "true", "yes"):
        turl = (os.getenv("TRACKER_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()
        if turl.startswith(("postgresql://", "postgres://")):
            try:
                import psycopg2  # noqa: F401
            except ImportError:
                warnings.append(
                    "Postgres tracker URL set but psycopg2 missing — install: pip install .[postgres]"
                )
        else:
            db_path = os.getenv("TRACKER_DB_PATH", "job_applications.db")
            p = Path(db_path)
            parent = p.parent if p.is_absolute() else Path.cwd() / p.parent
            if not parent.exists():
                try:
                    parent.mkdir(parents=True, exist_ok=True)
                except OSError as e:
                    warnings.append(f"TRACKER_DB_PATH parent not writable: {e}")
            elif not os.access(parent, os.W_OK):
                warnings.append(f"TRACKER_DB_PATH parent not writable: {parent}")

    if os.getenv("ARTIFACTS_S3_BUCKET", "").strip():
        try:
            import boto3  # noqa: F401
        except ImportError:
            warnings.append(
                "ARTIFACTS_S3_BUCKET set but boto3 missing — install: pip install .[s3]"
            )

    if jwt_secret:
        try:
            import jwt  # noqa: F401
        except ImportError:
            warnings.append("JWT_SECRET set but PyJWT missing — pip install .[auth]")

    if os.getenv("PROMETHEUS_METRICS", "").lower() in ("1", "true", "yes"):
        try:
            import prometheus_client  # noqa: F401
        except ImportError:
            warnings.append(
                "PROMETHEUS_METRICS=1 but prometheus_client missing — pip install .[metrics]"
            )

    return errors, warnings


def run_startup_checks(context: str = "app") -> None:
    """
    Run config validation. In strict mode (production or STRICT_STARTUP=1), exit on errors.
    """
    errors, warnings = collect_startup_report(context)
    for w in warnings:
        print(f"⚠️ Startup: {w}")
    for e in errors:
        print(f"❌ Startup: {e}")
    if errors and is_strict_startup():
        sys.exit(1)


def validate_profile_path() -> bool:
    """True if candidate profile exists or example template is available."""
    from services.profile_service import DEFAULT_PROFILE_PATH, EXAMPLE_PROFILE_PATH

    if DEFAULT_PROFILE_PATH.is_file():
        return True
    if EXAMPLE_PROFILE_PATH.is_file():
        print(f"⚠️ Startup: Using example profile. Copy to {DEFAULT_PROFILE_PATH} and edit.")
        return True
    return False
