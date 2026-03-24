"""ATS adapter registry (v1 stubs)."""

from providers.ats import describe_ats_platform, get_ats_adapter_for_job
from providers.job_source import ATS_GREENHOUSE, ATS_LINKEDIN_JOBS


def test_linkedin_jobs_adapter_allows_auto_v1():
    ad = get_ats_adapter_for_job({"url": "https://linkedin.com/jobs/view/1"})
    assert ad.provider_id == ATS_LINKEDIN_JOBS
    assert ad.supports_auto_apply_v1() is True


def test_greenhouse_adapter_no_auto_v1():
    ad = get_ats_adapter_for_job({"url": "https://boards.greenhouse.io/acme/jobs/1"})
    assert ad.provider_id == ATS_GREENHOUSE
    assert ad.supports_auto_apply_v1() is False


def test_describe_ats_platform_mcp_shape():
    d = describe_ats_platform(job_url="https://linkedin.com/jobs/view/9", apply_url="")
    assert d["listing_provider"] == ATS_LINKEDIN_JOBS
    assert d["supports_auto_apply_v1"] is True
    assert "manual_assist_capabilities" in d
    assert d["analyze_form_preview"]["status"] == "schema_hints"


def test_analyze_form_mcp_equivalent_shape():
    """Same payload shape as MCP ``analyze_form`` tool (adapter + platform minus duplicate preview)."""
    from providers.ats.registry import describe_ats_platform, get_ats_adapter_for_job

    job = {"url": "", "apply_url": "https://boards.greenhouse.io/c/j/1"}
    adapter = get_ats_adapter_for_job(job)
    preview = adapter.analyze_form(job["apply_url"])
    meta = describe_ats_platform(job_url="", apply_url=job["apply_url"])
    meta.pop("analyze_form_preview", None)
    assert preview["status"] == "schema_hints"
    assert meta["apply_target_provider"] == ATS_GREENHOUSE
