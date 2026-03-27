from __future__ import annotations

import pytest

from services.fit_engine import FitResult
from services import job_prefilter


def _fit(
    *,
    overall: int = 80,
    decision: str = "apply",
    seniority: int = 80,
    hard_blockers: list[str] | None = None,
) -> FitResult:
    return FitResult(
        role_family="ai_ml_engineer",
        seniority_band="mid",
        role_match_score=90,
        experience_match_score=85,
        seniority_match_score=seniority,
        overall_fit_score=overall,
        fit_decision=decision,
        fit_reasons=["Strong fit"],
        unsupported_requirements=[],
        hard_blockers=hard_blockers or [],
        requirement_evidence_map=[],
        supported_skills=[],
        missing_skills=[],
    )


def _allow_role(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(job_prefilter, "detect_role_family", lambda *_: "ai_ml_engineer")
    monkeypatch.setattr(job_prefilter, "infer_candidate_role_families", lambda *_: ["ai_ml_engineer"])


def test_prefilter_high_confidence(monkeypatch: pytest.MonkeyPatch):
    _allow_role(monkeypatch)
    monkeypatch.setattr(job_prefilter, "score_structured_fit", lambda *args, **kwargs: _fit())

    result = job_prefilter.prefilter_job(
        job_url="https://example.com/job/1",
        job_title="Machine Learning Engineer",
        company="ExampleCo",
        job_description="Python, ML, and AWS required.",
        location="Remote",
        work_type="remote",
        resume_text="Resume text",
        profile={},
        ats_score=60,
    )
    assert result["classification"] == job_prefilter.JobPrefilterResult.HIGH_CONFIDENCE


def test_prefilter_review_fit_on_seniority_mismatch(monkeypatch: pytest.MonkeyPatch):
    _allow_role(monkeypatch)
    monkeypatch.setattr(job_prefilter, "score_structured_fit", lambda *args, **kwargs: _fit(seniority=30))

    result = job_prefilter.prefilter_job(
        job_url="https://example.com/job/2",
        job_title="Senior ML Engineer",
        company="ExampleCo",
        job_description="Python, ML, and AWS required.",
        location="Remote",
        work_type="remote",
        resume_text="Resume text",
        profile={},
        ats_score=65,
    )
    assert result["classification"] == job_prefilter.JobPrefilterResult.REVIEW_FIT


def test_prefilter_skips_location_mismatch(monkeypatch: pytest.MonkeyPatch):
    _allow_role(monkeypatch)
    profile = {
        "application_locations": [
            {"label": "NYC", "city": "New York", "state_region": "NY", "country": "US", "remote_ok": False}
        ]
    }
    result = job_prefilter.prefilter_job(
        job_url="https://example.com/job/3",
        job_title="ML Engineer",
        company="ExampleCo",
        job_description="Python required.",
        location="San Francisco, CA",
        work_type="onsite",
        resume_text="Resume text",
        profile=profile,
        ats_score=70,
    )
    assert result["classification"] == job_prefilter.JobPrefilterResult.SKIP
    assert "Location" in result["reason"]


def test_prefilter_skips_work_auth_blocker(monkeypatch: pytest.MonkeyPatch):
    _allow_role(monkeypatch)
    profile = {"visa_status": "F1 OPT"}
    result = job_prefilter.prefilter_job(
        job_url="https://example.com/job/4",
        job_title="ML Engineer",
        company="ExampleCo",
        job_description="US citizens only.",
        location="Remote",
        work_type="remote",
        resume_text="Resume text",
        profile=profile,
        ats_score=70,
    )
    assert result["classification"] == job_prefilter.JobPrefilterResult.SKIP


def test_prefilter_skips_weak_fit(monkeypatch: pytest.MonkeyPatch):
    _allow_role(monkeypatch)
    monkeypatch.setattr(job_prefilter, "score_structured_fit", lambda *args, **kwargs: _fit(overall=30, decision="skip"))

    result = job_prefilter.prefilter_job(
        job_url="https://example.com/job/5",
        job_title="ML Engineer",
        company="ExampleCo",
        job_description="Python required.",
        location="Remote",
        work_type="remote",
        resume_text="Resume text",
        profile={},
        ats_score=10,
    )
    assert result["classification"] == job_prefilter.JobPrefilterResult.SKIP
