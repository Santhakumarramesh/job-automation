"""Pre-fit ranking service (resume overlap before deep fit/ATS)."""

from providers.common_schema import JobListing
from services.prefit_ranker import (
    prefit_score_job,
    rank_job_listings,
)


def test_prefit_score_job_title_match():
    kw = {"job_titles": ["Machine Learning Engineer"], "skills": [], "locations": []}
    job = JobListing(
        title="Senior Machine Learning Engineer",
        company="X",
        location="Remote",
        description="We use Python.",
    )
    assert prefit_score_job(job, kw) >= 30


def test_prefit_score_job_skill_in_description():
    kw = {"job_titles": ["Zebra"], "skills": ["Python"], "locations": []}
    job = JobListing(
        title="Developer",
        company="X",
        location="NYC",
        description="Must know Python and SQL.",
    )
    assert prefit_score_job(job, kw) >= 8


def test_rank_job_listings_orders_by_score():
    kw = {"job_titles": ["Data Scientist"], "skills": ["pandas"], "locations": ["Remote"]}
    low = JobListing(
        title="Chef",
        company="R",
        location="Paris",
        description="Cooking only.",
    )
    high = JobListing(
        title="Data Scientist — Analytics",
        company="A",
        location="Remote US",
        description="pandas numpy pipelines.",
    )
    out = rank_job_listings([low, high], keyword_bundle=kw)
    assert out[0].title.startswith("Data Scientist")
