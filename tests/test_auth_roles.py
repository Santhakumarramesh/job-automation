"""Phase 3.1.4 — admin role checks on User (no Celery import required)."""

import base64
import json
import os
from unittest.mock import patch

import jwt
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


def _b64url(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).decode().rstrip("=")


def test_jwt_auth_configured_with_jwks_only(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("JWT_JWKS_URL", "https://idp.example/jwks")
    from app.auth import jwt_auth_configured

    assert jwt_auth_configured()


def test_decode_jwt_prefers_hs256_when_secret_and_jwks_set(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "unit-test-secret-key-32chars!!")
    monkeypatch.setenv("JWT_JWKS_URL", "https://idp.example/jwks")
    from app.auth import _decode_jwt_identity

    token = jwt.encode({"sub": "hs-user"}, "unit-test-secret-key-32chars!!", algorithm="HS256")
    sub, roles, _ws = _decode_jwt_identity(f"Bearer {token}")
    assert sub == "hs-user"
    assert isinstance(roles, list)


def test_decode_jwt_rs256_uses_jwks_path(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("JWT_JWKS_URL", "https://idp.example/jwks")
    token = f"{_b64url({'alg': 'RS256', 'kid': 'k1'})}.{_b64url({'sub': 'rs-user'})}.sig"
    with patch("app.auth._decode_with_jwks", return_value={"sub": "rs-user", "roles": ["admin"]}):
        from app.auth import _decode_jwt_identity

        sub, roles, _ws = _decode_jwt_identity(f"Bearer {token}")
    assert sub == "rs-user"
    assert "admin" in roles
