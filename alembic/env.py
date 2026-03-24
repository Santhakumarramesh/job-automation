"""
Alembic environment for the application tracker Postgres database.

URL: TRACKER_DATABASE_URL (preferred) or DATABASE_URL — must be postgresql:// or postgres://.
SQLite tracker schema is managed by services/tracker_db.py (no Alembic).
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

try:
    from dotenv import load_dotenv

    _root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    load_dotenv(os.path.join(_root, ".env"))
except ImportError:
    pass

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def get_database_url() -> str:
    url = (os.getenv("TRACKER_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()
    if not url:
        raise RuntimeError(
            "Set TRACKER_DATABASE_URL or DATABASE_URL (PostgreSQL) before running Alembic."
        )
    if not url.startswith(("postgresql://", "postgres://")):
        raise RuntimeError(
            "Alembic targets PostgreSQL only. For SQLite, tracker schema is created by "
            "services.tracker_db.initialize_tracker_db()."
        )
    return url


def run_migrations_offline() -> None:
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {}) or {}
    configuration["sqlalchemy.url"] = get_database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
