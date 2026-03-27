"""Structured fit engine tests."""

from services.fit_engine import score_structured_fit


def test_good_fit_job_apply():
    resume_text = (
        "Senior Machine Learning Engineer with 6 years of experience. "
        "Python and PyTorch projects in production. "
        "AWS and S3 deployments. "
        "Built RAG systems and RAG evaluation."
    )
    job_title = "Senior Machine Learning Engineer"
    job_description = (
        "Requirements:\n"
        "- 5+ years of experience with Python and PyTorch\n"
        "- Experience deploying ML models to production\n"
        "- Experience with AWS and S3\n"
        "- RAG experience preferred\n"
    )
    profile = {"graduation_date": "2017"}
    fit = score_structured_fit(job_title, job_description, resume_text, profile)
    assert fit.fit_decision == "apply"
    assert fit.overall_fit_score >= 60
    assert any(r.status == "supported" for r in fit.requirement_evidence_map)


def test_review_fit_job_when_unsupported_requirements():
    resume_text = (
        "Machine Learning Engineer with 3 years of experience. "
        "Python and PyTorch for NLP pipelines."
    )
    job_title = "Machine Learning Engineer"
    job_description = (
        "Requirements:\n"
        "- 3+ years of experience with Python\n"
        "- Experience with Rust or Go\n"
        "- Experience with Kubernetes\n"
    )
    profile = {"graduation_date": "2021"}
    fit = score_structured_fit(job_title, job_description, resume_text, profile)
    assert fit.fit_decision == "review_fit"
    assert fit.unsupported_requirements


def test_hard_blocked_job():
    resume_text = "Machine Learning Engineer with Python experience."
    job_title = "ML Engineer"
    job_description = "US citizens only. Active security clearance required."
    fit = score_structured_fit(job_title, job_description, resume_text, {})
    assert fit.fit_decision == "skip"
    assert fit.hard_blockers


def test_seniority_mismatch_job():
    resume_text = "Junior ML Engineer with 1 year of experience. Python projects."
    job_title = "Principal Machine Learning Engineer"
    job_description = "10+ years of experience required."
    profile = {"graduation_date": "2024"}
    fit = score_structured_fit(job_title, job_description, resume_text, profile)
    assert fit.seniority_match_score <= 25
    assert fit.fit_decision in ("review_fit", "skip")


def test_unsupported_requirement_mapping():
    resume_text = "ML Engineer with Python experience."
    job_title = "ML Engineer"
    job_description = "Must have Kubernetes experience."
    fit = score_structured_fit(job_title, job_description, resume_text, {})
    unsupported = [r for r in fit.requirement_evidence_map if "kubernetes" in r.requirement.lower()]
    assert unsupported and unsupported[0].status == "unsupported"
