"""Static ATS form hints (v1 analyze_form)."""

from providers.ats.form_hints import build_form_hints
from providers.job_source import ATS_GREENHOUSE, ATS_LINKEDIN_JOBS, ATS_WORKDAY


def test_linkedin_jobs_hints():
    h = build_form_hints(ATS_LINKEDIN_JOBS, "https://linkedin.com/jobs/view/1")
    assert h["status"] == "schema_hints"
    assert h["flow"] == "linkedin_easy_apply_modal"
    assert "resume_upload" in str(h["typical_sections"])


def test_workday_multi_step_hints():
    h = build_form_hints(ATS_WORKDAY, "https://x.wd103.myworkdayjobs.com/job")
    assert h["flow"] == "workday_multi_step"
    assert any(s.get("id") == "questions" for s in h["typical_sections"])


def test_greenhouse_hints():
    h = build_form_hints(ATS_GREENHOUSE, "")
    assert "eeo" in str(h["typical_sections"]).lower() or any(
        "eeo" in (s.get("id") or "") for s in h["typical_sections"]
    )
