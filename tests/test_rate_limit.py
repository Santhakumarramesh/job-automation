"""Optional API rate limiting (services/rate_limit.py)."""

import os
from unittest.mock import patch

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


@pytest.mark.skipif(not _APP_OK, reason="app.main not importable")
def test_live_form_probe_separate_rate_limit(monkeypatch):
    """Dedicated bucket for POST /api/ats/analyze-form/live when env is set."""
    monkeypatch.delenv("API_RATE_LIMIT_ENABLED", raising=False)
    monkeypatch.setenv("API_RATE_LIMIT_LIVE_FORM_PROBE_PER_MINUTE", "2")
    from fastapi.testclient import TestClient

    app = _rate_limit_app
    body = {"job_url": "https://example.com/", "apply_url": ""}

    with TestClient(app) as client:
        assert client.post("/api/ats/analyze-form/live", json=body).status_code == 403
        assert client.post("/api/ats/analyze-form/live", json=body).status_code == 403
        r = client.post("/api/ats/analyze-form/live", json=body)
    assert r.status_code == 429
    assert r.json().get("detail") == "Live form probe rate limit exceeded"


@pytest.mark.skipif(not _APP_OK, reason="app.main not importable")
def test_ats_search_jobs_separate_rate_limit(monkeypatch):
    """Dedicated bucket for POST /api/ats/search-jobs when env is set."""
    monkeypatch.delenv("API_RATE_LIMIT_ENABLED", raising=False)
    monkeypatch.setenv("API_RATE_LIMIT_ATS_SEARCH_JOBS_PER_MINUTE", "2")
    from fastapi.testclient import TestClient

    app = _rate_limit_app
    body = {"keywords": "python", "max_results": 3}

    with patch("providers.linkedin_mcp_jobs.fetch_linkedin_mcp_jobs", return_value=[]):
        with TestClient(app) as client:
            assert client.post("/api/ats/search-jobs", json=body).status_code == 200
            assert client.post("/api/ats/search-jobs", json=body).status_code == 200
            r = client.post("/api/ats/search-jobs", json=body)
    assert r.status_code == 429
    assert r.json().get("detail") == "ATS search-jobs rate limit exceeded"


@pytest.mark.skipif(not _APP_OK, reason="app.main not importable")
def test_linkedin_browser_separate_rate_limit(monkeypatch):
    """Dedicated bucket for LinkedIn Playwright ATS routes when env is set."""
    monkeypatch.delenv("API_RATE_LIMIT_ENABLED", raising=False)
    monkeypatch.delenv("ATS_ALLOW_LINKEDIN_BROWSER", raising=False)
    monkeypatch.setenv("API_RATE_LIMIT_LINKEDIN_BROWSER_PER_MINUTE", "2")
    from fastapi.testclient import TestClient

    app = _rate_limit_app
    body_apply = {
        "jobs": [
            {
                "title": "Eng",
                "company": "Co",
                "url": "https://www.linkedin.com/jobs/view/1",
                "easy_apply_confirmed": True,
            }
        ],
        "dry_run": True,
    }

    with TestClient(app) as client:
        assert client.post("/api/ats/apply-to-jobs", json=body_apply).status_code == 403
        assert client.post("/api/ats/apply-to-jobs", json=body_apply).status_code == 403
        r = client.post("/api/ats/apply-to-jobs", json=body_apply)
    assert r.status_code == 429
    assert r.json().get("detail") == "LinkedIn browser automation rate limit exceeded"
