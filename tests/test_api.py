from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

try:
    from app.main import app
    client = TestClient(app)
    _APP_AVAILABLE = True
except ImportError:
    client = None
    app = None
    _APP_AVAILABLE = False


def test_extract_search_keywords():
    """Role keyword extraction from master resume."""
    from agents.master_resume_guard import extract_search_keywords
    text = "Machine learning engineer with Python TensorFlow SQL AWS. Experience at Google. Remote. " * 2  # >100 chars
    kw = extract_search_keywords(text)
    assert "job_titles" in kw
    assert "skills" in kw
    assert "locations" in kw
    assert any("python" in s.lower() for s in kw["skills"])
    assert len(kw["job_titles"]) >= 1


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "Job Automation API is active"}


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_openapi_schema_grouped_by_tags():
    schema = client.get("/openapi.json").json()
    assert schema["info"]["title"] == "Career Co-Pilot Pro API"
    assert schema["info"].get("version") == "0.1.0"
    tag_names = {t["name"] for t in schema.get("tags", [])}
    assert "jobs" in tag_names and "admin" in tag_names
    assert schema["paths"]["/api/jobs"]["post"]["tags"] == ["jobs"]
    assert schema["paths"]["/api/admin/applications"]["get"]["tags"] == ["admin"]


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_openapi_security_schemes_for_swagger_authorize():
    schema = client.get("/openapi.json").json()
    schemes = schema["components"]["securitySchemes"]
    assert schemes["BearerAuth"]["type"] == "http"
    assert schemes["BearerAuth"]["scheme"] == "bearer"
    assert schemes["ApiKeyAuth"]["type"] == "apiKey"
    assert schemes["ApiKeyAuth"]["name"] == "X-API-Key"
    sec = schema["paths"]["/api/jobs"]["post"]["security"]
    assert {} in sec
    assert {"BearerAuth": []} in sec
    assert {"ApiKeyAuth": []} in sec

@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_get_application_by_job_id():
    import os
    import tempfile
    from pathlib import Path

    import services.application_tracker as at
    from app.auth import User, get_current_user
    from app.main import app

    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "job_applications.csv"
        prev_csv = at.APPLICATION_FILE
        prev_db = os.environ.get("TRACKER_USE_DB")
        os.environ["TRACKER_USE_DB"] = "0"
        at.APPLICATION_FILE = csv_path
        try:
            at.initialize_tracker()
            at.log_application(
                {
                    "target_company": "APIco",
                    "target_position": "Eng",
                    "job_id": "api-job-99",
                    "user_id": "alice",
                    "artifacts_manifest": {"run_id": "r1"},
                }
            )
            app.dependency_overrides[get_current_user] = lambda: User("alice", [])
            c = TestClient(app)
            r = c.get("/api/applications/by-job/api-job-99")
            assert r.status_code == 200
            body = r.json()
            assert body["application"]["company"] == "APIco"
            assert body["artifacts"]["artifacts_manifest"]["run_id"] == "r1"
        finally:
            at.APPLICATION_FILE = prev_csv
            app.dependency_overrides.clear()
            if prev_db is None:
                os.environ.pop("TRACKER_USE_DB", None)
            else:
                os.environ["TRACKER_USE_DB"] = prev_db


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_submit_job():
    job_data = {
        "name": "Test Job",
        "payload": {"url": "https://example.com/job"},
    }
    with patch("app.main.enqueue_job", return_value="00000000-0000-0000-0000-000000000099"):
        response = client.post("/api/jobs", json=job_data)
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert body["job_id"] == "00000000-0000-0000-0000-000000000099"


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_submit_job_idempotency_header():
    job_data = {"name": "J", "payload": {}}
    mock = MagicMock(return_value="job-uuid-1")
    with patch("app.main.enqueue_job", mock):
        r = client.post("/api/jobs", json=job_data, headers={"Idempotency-Key": " k1 "})
    assert r.status_code == 202
    mock.assert_called_once()
    assert mock.call_args.kwargs["idempotency_key"] == "k1"


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_submit_job_idempotency_header_and_body_must_agree():
    job_data = {"name": "J", "payload": {}, "idempotency_key": "a"}
    with patch("app.main.enqueue_job", return_value="x"):
        r = client.post("/api/jobs", json=job_data, headers={"Idempotency-Key": "b"})
    assert r.status_code == 400


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_submit_job_idempotency_header_too_long():
    job_data = {"name": "J", "payload": {}}
    long_key = "x" * 201
    r = client.post("/api/jobs", json=job_data, headers={"Idempotency-Key": long_key})
    assert r.status_code == 400
