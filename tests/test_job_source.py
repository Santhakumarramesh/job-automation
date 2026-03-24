"""Job URL → ATS / board classification (policy + tracker hooks)."""

from providers.job_source import (
    ATS_DICE,
    ATS_GREENHOUSE,
    ATS_LEVER,
    ATS_LINKEDIN_JOBS,
    ATS_LINKEDIN_OTHER,
    ATS_OTHER,
    ATS_UNKNOWN,
    ATS_WORKDAY,
    ats_metadata_for_job,
    detect_ats_provider,
    is_linkedin_jobs_listing_url,
)


def test_detect_linkedin_jobs_view():
    assert detect_ats_provider("https://www.linkedin.com/jobs/view/123") == ATS_LINKEDIN_JOBS
    assert is_linkedin_jobs_listing_url("linkedin.com/jobs/collections/recommended/7")


def test_detect_linkedin_non_jobs():
    assert detect_ats_provider("https://linkedin.com/in/someone") == ATS_LINKEDIN_OTHER
    assert detect_ats_provider("https://www.linkedin.com/company/acme") == ATS_LINKEDIN_OTHER


def test_detect_external_boards():
    assert detect_ats_provider("https://boards.greenhouse.io/acme/jobs/1") == ATS_GREENHOUSE
    assert detect_ats_provider("https://jobs.lever.co/acme/uuid") == ATS_LEVER
    assert detect_ats_provider("https://acme.wd103.myworkdayjobs.com/External/job/x") == ATS_WORKDAY
    assert detect_ats_provider("https://www.dice.com/job-detail/abc") == ATS_DICE


def test_detect_unknown_and_other():
    assert detect_ats_provider("") == ATS_UNKNOWN
    assert detect_ats_provider("https://careers.google.com/jobs/results/1") == ATS_OTHER


def test_ats_metadata_for_job():
    m = ats_metadata_for_job(
        {
            "url": "https://linkedin.com/jobs/view/9",
            "apply_url": "https://boards.greenhouse.io/corp/1",
        }
    )
    assert m["ats_provider"] == ATS_LINKEDIN_JOBS
    assert m["ats_provider_apply_target"] == ATS_GREENHOUSE
