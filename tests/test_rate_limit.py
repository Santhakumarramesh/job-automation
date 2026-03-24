"""Optional API rate limiting (services/rate_limit.py)."""

import os

import pytest

try:
    from app.main import app as _rate_limit_app

    _APP_OK = True
except ImportError:
    _rate_limit_app = None
    _APP_OK = False


@pytest.fixture(autouse=True)
def _clear_rl():
    import services.rate_limit as rl

    rl.clear_rate_limit_state_for_tests()
    yield
    rl.clear_rate_limit_state_for_tests()


@pytest.mark.skipif(not _APP_OK, reason="app.main not importable")
def test_rate_limit_disabled_by_default():
    from fastapi.testclient import TestClient

    app = _rate_limit_app

    with TestClient(app) as client:
        for _ in range(5):
            assert client.get("/api/applications").status_code == 200


@pytest.mark.skipif(not _APP_OK, reason="app.main not importable")
def test_rate_limit_429_after_burst(monkeypatch):
    monkeypatch.setenv("API_RATE_LIMIT_ENABLED", "1")
    monkeypatch.setenv("API_RATE_LIMIT_PER_MINUTE", "2")
    from fastapi.testclient import TestClient

    app = _rate_limit_app

    with TestClient(app) as client:
        assert client.get("/api/applications").status_code == 200
        assert client.get("/api/applications").status_code == 200
        r = client.get("/api/applications")
    assert r.status_code == 429
    assert r.json().get("detail") == "Rate limit exceeded"
    assert "Retry-After" in r.headers


@pytest.mark.skipif(not _APP_OK, reason="app.main not importable")
def test_health_not_rate_limited(monkeypatch):
    monkeypatch.setenv("API_RATE_LIMIT_ENABLED", "1")
    monkeypatch.setenv("API_RATE_LIMIT_PER_MINUTE", "1")
    from fastapi.testclient import TestClient

    app = _rate_limit_app

    with TestClient(app) as client:
        assert client.get("/api/applications").status_code == 200
        assert client.get("/health").status_code == 200
        assert client.get("/health").status_code == 200


@pytest.mark.skipif(not _APP_OK, reason="app.main not importable")
def test_x_forwarded_for_when_trusted(monkeypatch):
    monkeypatch.setenv("API_RATE_LIMIT_ENABLED", "1")
    monkeypatch.setenv("API_RATE_LIMIT_PER_MINUTE", "1")
    monkeypatch.setenv("API_RATE_LIMIT_TRUST_X_FORWARDED_FOR", "1")
    from fastapi.testclient import TestClient

    app = _rate_limit_app

    with TestClient(app) as client:
        h = {"X-Forwarded-For": "203.0.113.50"}
        assert client.get("/api/applications", headers=h).status_code == 200
        assert client.get("/api/applications", headers=h).status_code == 429
        h2 = {"X-Forwarded-For": "203.0.113.51"}
        assert client.get("/api/applications", headers=h2).status_code == 200
