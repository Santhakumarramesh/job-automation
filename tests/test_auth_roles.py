"""Phase 3.1.4 — admin role checks on User (no Celery import required)."""

import os

import pytest


@pytest.fixture
def clear_admin_env(monkeypatch):
    monkeypatch.setenv("JWT_ADMIN_ROLES", "admin,superuser")
    yield
    monkeypatch.delenv("JWT_ADMIN_ROLES", raising=False)


def test_user_is_admin_by_role(clear_admin_env):
    from app.auth import User

    assert User("u1", ["admin"]).is_admin
    assert User("u2", ["superuser"]).is_admin
    assert not User("u3", ["user", "viewer"]).is_admin
    assert not User("u4", []).is_admin


def test_jwt_roles_from_payload_merges_claims(clear_admin_env):
    from app.auth import _jwt_roles_from_payload

    roles = _jwt_roles_from_payload(
        {
            "role": "Admin",
            "roles": ["viewer"],
            "realm_access": {"roles": ["superuser"]},
        }
    )
    assert "admin" in roles
    assert "viewer" in roles
    assert "superuser" in roles


def test_admin_role_set_empty_means_no_admin(clear_admin_env, monkeypatch):
    monkeypatch.setenv("JWT_ADMIN_ROLES", "")
    from app.auth import User, _admin_role_set

    assert _admin_role_set() == set()
    assert not User("x", ["admin"]).is_admin
