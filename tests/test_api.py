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


def test_batch_prioritize_jobs_payload_empty():
    from services.batch_prioritize_jobs import batch_prioritize_jobs_payload

    assert batch_prioritize_jobs_payload([], "resume text " * 20)["status"] == "error"


def test_review_unmapped_fields_payload():
    from services.run_results_reports import review_unmapped_fields_payload

    out = review_unmapped_fields_payload(
        [
            {"unmapped_fields": ["Salary expectation", "Sponsorship required"]},
            {"unmapped_fields": ["Salary expectation"]},
        ]
    )
    assert out["status"] == "ok"
    assert out["total_unmapped"] == 3
    assert out["unmapped_summary"].get("Salary expectation") == 2


def test_application_audit_report_payload():
    from services.run_results_reports import application_audit_report_payload

    out = application_audit_report_payload(
        [
            {"status": "applied", "unmapped_fields": ["a"]},
            {"status": "failed", "error": "timeout"},
            {"status": "dry_run"},
        ]
    )
    assert out["status"] == "ok"
    assert out["applied"] == 1
    assert out["failed"] == 1
    assert out["dry_run"] == 1
    assert out.get("shadow_would_apply") == 0
    assert out.get("shadow_would_not_apply") == 0
    assert "timeout" in (out.get("fail_reasons") or [])

    out2 = application_audit_report_payload(
        [
            {"status": "shadow_would_apply"},
            {"status": "shadow_would_not_apply", "error": "x"},
        ]
    )
    assert out2["shadow_would_apply"] == 1
    assert out2["shadow_would_not_apply"] == 1


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_post_ats_autofill_values_no_profile(monkeypatch):
    monkeypatch.setattr("services.profile_service.load_profile", lambda: {})
    r = client.post("/api/ats/autofill-values", json={"form_type": "linkedin"})
    assert r.status_code == 200
    assert r.json().get("status") == "no_profile"


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
@patch("enhanced_ats_checker.EnhancedATSChecker")
def test_post_ats_batch_prioritize_jobs_mocked(mock_checker_cls):
    inst = MagicMock()
    inst.comprehensive_ats_check.return_value = {"ats_score": 91}
    mock_checker_cls.return_value = inst
    jd = "Senior Python engineer with AWS kubernetes docker. " * 15
    resume = "Python developer with AWS and APIs experience. " * 15
    job = {
        "title": "Engineer",
        "company": "ACME",
        "description": jd,
        "url": "https://example.com/j",
        "easy_apply_confirmed": True,
    }
    r = client.post(
        "/api/ats/batch-prioritize-jobs",
        json={"jobs": [job], "master_resume_text": resume, "max_scored": 5},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("status") == "ok"
    assert len(data.get("prioritized") or []) == 1
    assert data["prioritized"][0].get("ats_score") == 91


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_post_ats_batch_prioritize_jobs_too_many():
    r = client.post(
        "/api/ats/batch-prioritize-jobs",
        json={"jobs": [{"description": "x" * 120}] * 501, "master_resume_text": "y" * 200},
    )
    assert r.status_code == 400


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_post_ats_prepare_application_package_mocked(monkeypatch):
    monkeypatch.setattr(
        "services.profile_service.load_profile",
        lambda: {"full_name": "Ada Lovelace", "email": "ada@example.com"},
    )
    monkeypatch.setattr(
        "services.resume_naming.ensure_resume_exists_for_job",
        lambda *args, **kwargs: "/tmp/Ada_Role_at_Co_Resume.pdf",
    )

    def _fake_aq(question_text, profile=None, job_context=None, **kwargs):
        return {
            "answer": "ok",
            "manual_review_required": False,
            "reason_codes": [],
            "classified_type": "generic",
        }

    monkeypatch.setattr("agents.application_answerer.answer_question_structured", _fake_aq)
    r = client.post(
        "/api/ats/prepare-application-package",
        json={"job_title": "Engineer", "company": "ACME"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("status") == "ok"
    assert data.get("resume_path")
    av = data.get("autofill_values") or {}
    assert av.get("email") == "ada@example.com"
    assert av.get("first_name") == "Ada"


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_post_ats_review_unmapped_fields():
    r = client.post(
        "/api/ats/review-unmapped-fields",
        json={"run_results": [{"unmapped_fields": ["Years of Python"]}]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("status") == "ok"
    assert data.get("total_unmapped") == 1


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_post_ats_application_audit_report():
    r = client.post(
        "/api/ats/application-audit-report",
        json={"run_results": [{"status": "skipped", "unmapped_fields": ["x", "x"]}]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("skipped") == 1
    assert data.get("unmapped_fields_count") == 2


def test_apply_to_jobs_payload_bad_json():
    from services.linkedin_browser_automation import apply_to_jobs_payload

    assert apply_to_jobs_payload("not-json")["status"] == "error"
    assert apply_to_jobs_payload("[]")["status"] == "error"


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_post_ats_prepare_resume_for_job_mocked(monkeypatch):
    monkeypatch.setattr(
        "services.resume_naming.ensure_resume_exists_for_job",
        lambda *args, **kwargs: "/tmp/Candidate_Role_at_ACME_Resume.pdf",
    )
    r = client.post(
        "/api/ats/prepare-resume-for-job",
        json={"job_title": "Role", "company": "ACME"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("status") == "ready"
    assert data.get("filename")


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_post_ats_confirm_easy_apply_disabled(monkeypatch):
    monkeypatch.delenv("ATS_ALLOW_LINKEDIN_BROWSER", raising=False)
    r = client.post(
        "/api/ats/confirm-easy-apply",
        json={"job_url": "https://www.linkedin.com/jobs/view/123"},
    )
    assert r.status_code == 403
    assert r.json().get("status") == "disabled"


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_post_ats_apply_to_jobs_disabled(monkeypatch):
    monkeypatch.delenv("ATS_ALLOW_LINKEDIN_BROWSER", raising=False)
    r = client.post(
        "/api/ats/apply-to-jobs",
        json={
            "jobs": [
                {
                    "title": "Eng",
                    "company": "Co",
                    "url": "https://www.linkedin.com/jobs/view/1",
                    "easy_apply_confirmed": True,
                }
            ],
            "dry_run": True,
        },
    )
    assert r.status_code == 403


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_post_ats_apply_to_jobs_dry_run_disabled(monkeypatch):
    monkeypatch.delenv("ATS_ALLOW_LINKEDIN_BROWSER", raising=False)
    r = client.post(
        "/api/ats/apply-to-jobs/dry-run",
        json={
            "jobs": [
                {
                    "title": "Eng",
                    "company": "Co",
                    "url": "https://www.linkedin.com/jobs/view/1",
                    "easy_apply_confirmed": True,
                }
            ],
        },
    )
    assert r.status_code == 403


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
@patch("services.linkedin_browser_automation.apply_to_jobs_payload")
def test_post_ats_apply_to_jobs_dry_run_enabled_forces_dry_run(mock_payload, monkeypatch):
    monkeypatch.setenv("ATS_ALLOW_LINKEDIN_BROWSER", "1")
    mock_payload.return_value = {"status": "ok", "applied": 0, "total": 1, "results": [], "results_file": "/tmp/x"}
    client.post(
        "/api/ats/apply-to-jobs/dry-run",
        json={
            "jobs": [
                {
                    "title": "Eng",
                    "company": "Co",
                    "url": "https://www.linkedin.com/jobs/view/1",
                    "easy_apply_confirmed": True,
                }
            ],
            "rate_limit_seconds": 30.0,
        },
    )
    mock_payload.assert_called_once()
    ca = mock_payload.call_args
    assert ca.kwargs.get("dry_run") is True
    assert ca.kwargs.get("rate_limit_seconds") == 30.0


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
@patch("services.linkedin_browser_automation.apply_to_jobs_payload")
def test_post_ats_apply_to_jobs_enabled_mocked(mock_payload, monkeypatch):
    monkeypatch.setenv("ATS_ALLOW_LINKEDIN_BROWSER", "1")
    mock_payload.return_value = {
        "status": "ok",
        "applied": 0,
        "total": 1,
        "results": [],
        "results_file": "/tmp/run.json",
    }
    r = client.post(
        "/api/ats/apply-to-jobs",
        json={
            "jobs": [
                {
                    "title": "Eng",
                    "company": "Co",
                    "url": "https://www.linkedin.com/jobs/view/1",
                    "easy_apply_confirmed": True,
                }
            ],
            "dry_run": True,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json().get("status") == "ok"
    mock_payload.assert_called_once()


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
@patch("services.linkedin_browser_automation.confirm_easy_apply_payload")
def test_post_ats_confirm_easy_apply_enabled_mocked(mock_confirm, monkeypatch):
    monkeypatch.setenv("ATS_ALLOW_LINKEDIN_BROWSER", "1")
    mock_confirm.return_value = {
        "easy_apply_confirmed": True,
        "status": "ok",
        "url": "https://www.linkedin.com/jobs/view/123",
        "matched_selector": "button",
        "selectors_tried": [],
    }
    r = client.post(
        "/api/ats/confirm-easy-apply",
        json={"job_url": "https://www.linkedin.com/jobs/view/123"},
    )
    assert r.status_code == 200, r.text
    assert r.json().get("easy_apply_confirmed") is True


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
@patch("langchain_openai.ChatOpenAI")
def test_post_ats_generate_recruiter_followup_mocked(mock_llm_cls, monkeypatch):
    monkeypatch.setattr(
        "services.profile_service.load_profile",
        lambda: {"full_name": "Test User"},
    )
    inst = MagicMock()
    inst.invoke.return_value = MagicMock(
        content='{"linkedin_message": "Hello", "email_subject": "Re role", "email_body": "Thanks"}'
    )
    mock_llm_cls.return_value = inst
    r = client.post(
        "/api/ats/generate-recruiter-followup",
        json={"job_title": "PM", "company": "Co", "application_date": "2025-01-01"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("status") == "ok"
    assert data.get("linkedin_message") == "Hello"


def test_detect_form_type_payload_empty_url():
    from services.form_type_detection import detect_form_type_payload

    out = detect_form_type_payload("")
    assert out.get("form_type") == "generic"
    assert out.get("error")


def test_linkedin_mcp_search_jobs_payload_blank_keywords():
    from providers.linkedin_mcp_jobs import linkedin_mcp_search_jobs_payload

    assert linkedin_mcp_search_jobs_payload(keywords="")["status"] == "error"
    assert linkedin_mcp_search_jobs_payload(keywords="   ")["status"] == "error"


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
def test_get_ats_platform():
    r = client.get(
        "/api/ats/platform",
        params={"job_url": "https://linkedin.com/jobs/view/1", "apply_url": "https://boards.greenhouse.io/x/jobs/9"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("status") == "ok"
    assert data.get("listing_provider") == "linkedin_jobs"
    assert data.get("apply_target_provider") == "greenhouse"
    assert data.get("supports_auto_apply_v1") is False


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_post_ats_truth_inventory_inline():
    long_text = "Python AWS machine learning engineer with distributed systems. " * 12
    r = client.post("/api/ats/truth-inventory", json={"master_resume_text": long_text})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("status") == "ok"
    assert data.get("char_count", 0) >= 100
    inv = data.get("inventory") or {}
    assert isinstance(inv.get("skills"), list)


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_post_ats_truth_inventory_rejects_path_traversal():
    r = client.post("/api/ats/truth-inventory", json={"master_resume_path": "../.env"})
    assert r.status_code == 400


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_post_ats_truth_inventory_rejects_absolute_path():
    r = client.post("/api/ats/truth-inventory", json={"master_resume_path": "/etc/passwd"})
    assert r.status_code == 400


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_post_ats_search_jobs_empty_keywords():
    r = client.post("/api/ats/search-jobs", json={"keywords": ""})
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "error"
    assert data.get("count") == 0


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
@patch("providers.linkedin_mcp_jobs.fetch_linkedin_mcp_jobs")
def test_post_ats_search_jobs_mocked(mock_fetch):
    from providers.common_schema import JobListing

    mock_fetch.return_value = [
        JobListing(
            title="Engineer",
            company="ACME",
            location="Remote",
            description="Build things",
            url="https://www.linkedin.com/jobs/view/1/",
            job_id="1",
        )
    ]
    r = client.post("/api/ats/search-jobs", json={"keywords": "python", "max_results": 5})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("status") == "ok"
    assert data.get("count") == 1
    assert data["jobs"][0].get("title") == "Engineer"
    mock_fetch.assert_called_once()


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
@patch("services.ats_service.EnhancedATSChecker")
def test_post_ats_score_job_fit_mocked(mock_checker_cls):
    inst = MagicMock()
    inst.comprehensive_ats_check.return_value = {
        "ats_score": 88,
        "detailed_breakdown": {"missing_keywords": ["kubernetes"]},
        "unsupported_requirements": [],
        "truthful_missing_keywords": [],
    }
    mock_checker_cls.return_value = inst
    jd = "Senior Python engineer with cloud and AWS experience required. " * 12
    resume = "Python developer with AWS and REST APIs experience. " * 12
    r = client.post(
        "/api/ats/score-job-fit",
        json={
            "job_description": jd,
            "master_resume_text": resume,
            "job_title": "Engineer",
            "company": "ACME",
            "location": "USA",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("status") == "ok"
    assert data.get("ats_score") == 88
    assert "fit_decision" in data
    assert isinstance(data.get("missing_keywords"), list)


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_post_ats_address_for_job(monkeypatch):
    monkeypatch.setattr(
        "services.profile_service.load_profile",
        lambda: {
            "full_name": "Jane Doe",
            "mailing_address": {"city": "Austin", "state": "TX", "country": "USA"},
            "alternate_mailing_addresses": [],
        },
    )
    r = client.post(
        "/api/ats/address-for-job",
        json={"job_location": "Remote", "job_title": "Engineer"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("status") == "ok"
    assert data.get("used_alternate") is False
    assert "mailing_address_oneline" in data


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_get_ats_form_type_linkedin():
    r = client.get(
        "/api/ats/form-type",
        params={"url": "https://www.linkedin.com/jobs/view/123/"},
    )
    assert r.status_code == 200, r.text
    assert r.json().get("form_type") == "linkedin"


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_post_ats_validate_profile_rejects_path_traversal():
    r = client.post("/api/ats/validate-profile", json={"profile_path": "../.env"})
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "error"
    assert "project" in (data.get("message") or "").lower()


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_post_ats_decide_apply_mode_skip_on_reject_fit():
    r = client.post(
        "/api/ats/decide-apply-mode",
        json={
            "job": {"url": "https://www.linkedin.com/jobs/view/123/", "easy_apply_confirmed": True},
            "fit_decision": "reject",
            "ats_score": 95,
            "unsupported_requirements": [],
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("status") == "ok"
    assert data.get("apply_mode") == "skip"


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_post_ats_application_decision_skip():
    r = client.post(
        "/api/ats/application-decision",
        json={
            "job": {
                "url": "https://www.linkedin.com/jobs/view/123/",
                "easy_apply_confirmed": True,
                "fit_decision": "reject",
            },
            "profile_path": "config/candidate_profile.example.json",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("schema_version") == "0.1"
    assert data.get("job_state") == "skip"
    assert data.get("safe_to_submit") is False


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_post_ats_application_decision_profile_path_traversal():
    r = client.post(
        "/api/ats/application-decision",
        json={"job": {}, "profile_path": "../.env"},
    )
    assert r.status_code == 400


def test_decide_apply_mode_payload_skip_without_app():
    from services.policy_service import decide_apply_mode_payload

    out = decide_apply_mode_payload(
        job={"url": "https://www.linkedin.com/jobs/view/1/"},
        fit_decision="reject",
        ats_score=95,
        unsupported_requirements=[],
    )
    assert out.get("status") == "ok"
    assert out.get("apply_mode") == "skip"


def test_score_job_fit_payload_returns_error_on_checker_failure():
    from services.ats_service import score_job_fit_payload

    with patch("services.ats_service.EnhancedATSChecker", side_effect=RuntimeError("checker down")):
        out = score_job_fit_payload("job description text " * 20, "master resume text " * 20)
    assert out.get("status") == "error"
    assert "checker down" in (out.get("message") or "")


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_post_ats_analyze_form_live_disabled(monkeypatch):
    monkeypatch.delenv("ATS_ALLOW_LIVE_FORM_PROBE", raising=False)
    r = client.post(
        "/api/ats/analyze-form/live",
        json={"job_url": "https://example.com/", "apply_url": ""},
    )
    assert r.status_code == 403
    data = r.json()
    assert data.get("status") == "disabled"
    assert "ATS_ALLOW_LIVE_FORM_PROBE" in (data.get("message") or "")


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_post_ats_analyze_form():
    r = client.post(
        "/api/ats/analyze-form",
        json={"job_url": "https://boards.greenhouse.io/acme/jobs/1", "apply_url": ""},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("status") == "ok"
    assert data.get("provider_id") == "greenhouse"
    fa = data.get("form_analysis") or {}
    assert fa.get("status") == "schema_hints"
    assert fa.get("flow") == "greenhouse_embedded_or_standalone"


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
    assert "jobs" in tag_names and "admin" in tag_names and "ats" in tag_names
    paths = schema.get("paths") or {}
    assert "/api/ats/truth-inventory" in paths
    assert "/api/ats/search-jobs" in paths
    assert "/api/ats/score-job-fit" in paths
    assert "/api/ats/address-for-job" in paths
    assert "/api/ats/decide-apply-mode" in paths
    assert "/api/ats/application-decision" in paths
    assert "/api/ats/form-type" in paths
    assert "/api/ats/validate-profile" in paths
    assert "/api/ats/autofill-values" in paths
    assert "/api/ats/batch-prioritize-jobs" in paths
    assert "/api/ats/prepare-application-package" in paths
    assert "/api/ats/review-unmapped-fields" in paths
    assert "/api/ats/application-audit-report" in paths
    assert "/api/ats/generate-recruiter-followup" in paths
    assert "/api/ats/prepare-resume-for-job" in paths
    assert "/api/ats/confirm-easy-apply" in paths
    assert "/api/ats/apply-to-jobs" in paths
    assert "/api/ats/apply-to-jobs/dry-run" in paths
    assert schema["paths"]["/api/jobs"]["post"]["tags"] == ["jobs"]
    assert schema["paths"]["/api/v1/jobs"]["post"]["tags"] == ["jobs"]
    assert schema["paths"]["/api/admin/applications"]["get"]["tags"] == ["admin"]
    assert "/api/admin/celery/inspect" in paths
    assert schema["paths"]["/api/admin/celery/inspect"]["get"]["tags"] == ["admin"]
    assert "/api/admin/apply-runner-metrics" in paths
    assert schema["paths"]["/api/admin/apply-runner-metrics"]["get"]["tags"] == ["admin"]
    assert "/api/admin/tracker-analytics/summary" in paths
    assert schema["paths"]["/api/admin/tracker-analytics/summary"]["get"]["tags"] == ["admin"]
    assert "/api/admin/applications/export" in paths
    assert "/api/admin/applications/by-user" in paths


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_openapi_security_schemes_for_swagger_authorize():
    schema = client.get("/openapi.json").json()
    schemes = schema["components"]["securitySchemes"]
    assert schemes["BearerAuth"]["type"] == "http"
    assert schemes["BearerAuth"]["scheme"] == "bearer"
    assert schemes["ApiKeyAuth"]["type"] == "apiKey"
    assert schemes["ApiKeyAuth"]["name"] == "X-API-Key"
    assert schemes["M2MApiKeyAuth"]["type"] == "apiKey"
    assert schemes["M2MApiKeyAuth"]["name"] == "X-M2M-API-Key"
    sec = schema["paths"]["/api/jobs"]["post"]["security"]
    assert {} in sec
    assert {"BearerAuth": []} in sec
    assert {"ApiKeyAuth": []} in sec
    assert {"M2MApiKeyAuth": []} in sec


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_m2m_api_key_sets_user_on_enqueue(monkeypatch):
    monkeypatch.setenv("M2M_API_KEY", "m2m-worker-secret-key-12345")
    monkeypatch.setenv("M2M_USER_ID", "worker-pod-7")
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    job_data = {"name": "W", "payload": {}}
    with patch("app.main.enqueue_job") as mock_enqueue:
        mock_enqueue.return_value = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        r = client.post(
            "/api/jobs",
            json=job_data,
            headers={"X-M2M-API-Key": "m2m-worker-secret-key-12345"},
        )
    assert r.status_code == 202
    assert mock_enqueue.call_args[0][2] == "worker-pod-7"


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_m2m_api_key_wrong_returns_401(monkeypatch):
    monkeypatch.setenv("M2M_API_KEY", "m2m-worker-secret-key-12345")
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    job_data = {"name": "W", "payload": {}}
    r = client.post(
        "/api/jobs",
        json=job_data,
        headers={"X-M2M-API-Key": "not-the-right-secret-key-123"},
    )
    assert r.status_code == 401


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_m2m_custom_header_name(monkeypatch):
    monkeypatch.setenv("M2M_API_KEY", "shared-m2m-secret-key-123456")
    monkeypatch.setenv("M2M_API_KEY_HEADER", "X-Worker-Key")
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    job_data = {"name": "W", "payload": {}}
    with patch("app.main.enqueue_job") as mock_enqueue:
        mock_enqueue.return_value = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        r = client.post(
            "/api/jobs",
            json=job_data,
            headers={"X-Worker-Key": "shared-m2m-secret-key-123456"},
        )
    assert r.status_code == 202
    assert mock_enqueue.call_args[0][2] == "m2m-service"


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
def test_submit_job_v1_path_alias():
    job_data = {"name": "V1 Job", "payload": {"url": "https://example.com/j"}}
    with patch("app.main.enqueue_job", return_value="11111111-1111-1111-1111-111111111111"):
        response = client.post("/api/v1/jobs", json=job_data)
    assert response.status_code == 202
    assert response.json()["job_id"] == "11111111-1111-1111-1111-111111111111"


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
    assert body["run_id"] == body["job_id"]


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


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_admin_celery_inspect_ok(monkeypatch):
    monkeypatch.setenv("API_KEY", "admkey")
    monkeypatch.setenv("API_KEY_IS_ADMIN", "1")
    monkeypatch.delenv("CELERY_ADMIN_INSPECT", raising=False)
    with patch(
        "services.celery_admin_inspect.celery_inspect_snapshot",
        return_value={"ok": True, "timeout_sec": 2.0, "workers": {"ping": {}}},
    ):
        r = client.get("/api/admin/celery/inspect", headers={"X-API-Key": "admkey"})
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert "workers" in body


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_admin_celery_inspect_forbidden_when_disabled(monkeypatch):
    monkeypatch.setenv("API_KEY", "admkey")
    monkeypatch.setenv("API_KEY_IS_ADMIN", "1")
    monkeypatch.setenv("CELERY_ADMIN_INSPECT", "0")
    r = client.get("/api/admin/celery/inspect", headers={"X-API-Key": "admkey"})
    assert r.status_code == 403


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_admin_tracker_analytics_summary_ok(monkeypatch):
    monkeypatch.setenv("API_KEY", "admkey")
    monkeypatch.setenv("API_KEY_IS_ADMIN", "1")
    import pandas as pd

    from services.application_tracker import TRACKER_COLUMNS

    df = pd.DataFrame(
        [
            {
                **{c: "" for c in TRACKER_COLUMNS},
                "status": "Applied",
                "submission_status": "Applied",
                "recruiter_response": "Pending",
                "user_id": "alice",
            },
        ]
    )
    with patch("services.application_tracker.load_applications", return_value=df):
        r = client.get("/api/admin/tracker-analytics/summary", headers={"X-API-Key": "admkey"})
    assert r.status_code == 200
    body = r.json()
    assert body.get("rows_analyzed") == 1
    assert body.get("applied_row_count") == 1
    assert body.get("truncated") is False


def test_admin_apply_runner_metrics_ok(monkeypatch):
    monkeypatch.setenv("API_KEY", "admkey")
    monkeypatch.setenv("API_KEY_IS_ADMIN", "1")
    fake = {"enabled": False, "hash": "apply_runner:metrics", "fields": {}}
    with patch(
        "services.apply_runner_metrics_redis.read_apply_runner_metrics_summary",
        return_value=fake,
    ):
        r = client.get("/api/admin/apply-runner-metrics", headers={"X-API-Key": "admkey"})
    assert r.status_code == 200
    assert r.json() == fake


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_admin_export_tracker_requires_admin(monkeypatch):
    monkeypatch.setenv("API_KEY", "userkey")
    monkeypatch.setenv("API_KEY_IS_ADMIN", "0")
    r = client.get("/api/admin/applications/export", params={"user_id": "u1"}, headers={"X-API-Key": "userkey"})
    assert r.status_code == 403


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_admin_export_tracker_ok(monkeypatch):
    monkeypatch.setenv("API_KEY", "admkey")
    monkeypatch.setenv("API_KEY_IS_ADMIN", "1")
    with patch("services.application_tracker.load_applications") as la:
        import pandas as pd

        la.return_value = pd.DataFrame([{"id": "1", "user_id": "alice", "job_id": "j1"}])
        r = client.get("/api/admin/applications/export", params={"user_id": "alice"}, headers={"X-API-Key": "admkey"})
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == "alice"
    assert body["count"] == 1
    assert body.get("workspace_id_filter") is None


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_submit_job_workspace_id_in_payload(monkeypatch):
    monkeypatch.setenv("API_KEY", "k")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    job_data = {"name": "W", "payload": {}, "workspace_id": "acme-corp"}
    with patch("app.main.enqueue_job") as mock_enqueue:
        mock_enqueue.return_value = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        r = client.post("/api/jobs", json=job_data, headers={"X-API-Key": "k"})
    assert r.status_code == 202
    payload = mock_enqueue.call_args[0][1]
    assert payload["workspace_id"] == "acme-corp"


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_submit_job_workspace_enforced_when_env(monkeypatch):
    from app.auth import User, get_current_user
    from app.main import app

    monkeypatch.setenv("API_ENFORCE_USER_WORKSPACE_ON_WRITES", "1")
    monkeypatch.delenv("API_WORKSPACE_ENFORCE_FOR_ADMIN", raising=False)
    app.dependency_overrides[get_current_user] = lambda: User("alice", [], workspace_id="ws-ok")
    try:
        job_data = {"name": "T", "payload": {"workspace_id": "ws-bad"}}
        with patch("app.main.enqueue_job", return_value="x"):
            r = client.post("/api/jobs", json=job_data)
        assert r.status_code == 403

        job_data2 = {"name": "T2", "payload": {}}
        with patch("app.main.enqueue_job") as mock_enqueue:
            mock_enqueue.return_value = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
            r2 = client.post("/api/jobs", json=job_data2)
        assert r2.status_code == 202
        assert mock_enqueue.call_args[0][1]["workspace_id"] == "ws-ok"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_list_applications_workspace_query_and_user_default():
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
            base = {
                "target_company": "Co",
                "target_position": "Eng",
                "user_id": "alice",
                "job_description": "d",
            }
            at.log_application({**base, "job_id": "jw1", "workspace_id": "w1"})
            at.log_application({**base, "job_id": "jw2", "workspace_id": "w2"})
            c = TestClient(app)
            app.dependency_overrides[get_current_user] = lambda: User("alice", [])
            r = c.get("/api/applications", params={"workspace_id": "w1"})
            assert r.status_code == 200
            assert r.json()["count"] == 1
            assert r.json()["items"][0]["job_id"] == "jw1"

            app.dependency_overrides[get_current_user] = lambda: User("alice", [], workspace_id="w2")
            r2 = c.get("/api/applications")
            assert r2.status_code == 200
            assert r2.json()["count"] == 1
            assert r2.json()["items"][0]["job_id"] == "jw2"

            r3 = c.get("/api/applications", params={"workspace_id": ""})
            assert r3.status_code == 200
            assert r3.json()["count"] == 2
        finally:
            at.APPLICATION_FILE = prev_csv
            app.dependency_overrides.clear()
            if prev_db is None:
                os.environ.pop("TRACKER_USE_DB", None)
            else:
                os.environ["TRACKER_USE_DB"] = prev_db


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_admin_delete_tracker_confirm_mismatch(monkeypatch):
    monkeypatch.setenv("API_KEY", "admkey")
    monkeypatch.setenv("API_KEY_IS_ADMIN", "1")
    r = client.delete(
        "/api/admin/applications/by-user",
        params={"user_id": "alice", "confirm_user_id": "bob"},
        headers={"X-API-Key": "admkey"},
    )
    assert r.status_code == 400


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_admin_delete_tracker_ok(monkeypatch):
    monkeypatch.setenv("API_KEY", "admkey")
    monkeypatch.setenv("API_KEY_IS_ADMIN", "1")
    with patch("services.application_tracker.delete_applications_for_user", return_value=3) as d, patch(
        "services.idempotency_db.delete_idempotency_rows_for_user", return_value=1,
    ):
        r = client.delete(
            "/api/admin/applications/by-user",
            params={"user_id": "alice", "confirm_user_id": "alice"},
            headers={"X-API-Key": "admkey"},
        )
    assert r.status_code == 200
    assert r.json()["deleted"] == 3
    assert r.json()["idempotency_deleted"] == 1
    d.assert_called_once_with("alice")


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_admin_celery_inspect_requires_admin(monkeypatch):
    monkeypatch.setenv("API_KEY", "userkey")
    monkeypatch.setenv("API_KEY_IS_ADMIN", "0")
    monkeypatch.delenv("CELERY_ADMIN_INSPECT", raising=False)
    r = client.get("/api/admin/celery/inspect", headers={"X-API-Key": "userkey"})
    assert r.status_code == 403


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_admin_apply_runner_metrics_requires_admin(monkeypatch):
    monkeypatch.setenv("API_KEY", "userkey")
    monkeypatch.setenv("API_KEY_IS_ADMIN", "0")
    r = client.get("/api/admin/apply-runner-metrics", headers={"X-API-Key": "userkey"})
    assert r.status_code == 403


@pytest.mark.skipif(not _APP_AVAILABLE, reason="app deps not installed")
def test_admin_tracker_analytics_requires_admin(monkeypatch):
    monkeypatch.setenv("API_KEY", "userkey")
    monkeypatch.setenv("API_KEY_IS_ADMIN", "0")
    r = client.get("/api/admin/tracker-analytics/summary", headers={"X-API-Key": "userkey"})
    assert r.status_code == 403
