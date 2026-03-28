from __future__ import annotations

import pytest


def test_job_analyzer_fallback_when_router_unavailable(monkeypatch: pytest.MonkeyPatch):
    from agents import job_analyzer as ja

    monkeypatch.setattr(
        ja.model_router,
        "generate_json",
        lambda **kwargs: {"status": "error", "message": "provider_down", "data": {}},
    )

    out = ja.analyze_job_description({"job_description": "Python, SQL role"})
    assert out["is_eligible"] is True
    assert "supervised review" in out["eligibility_reason"]


def test_ats_scorer_fallback_when_router_unavailable(monkeypatch: pytest.MonkeyPatch):
    from agents import ats_scorer as ats

    monkeypatch.setattr(
        ats.model_router,
        "generate_json",
        lambda **kwargs: {"status": "error", "message": "provider_down", "data": {}},
    )

    out = ats.score_resume(
        {
            "is_eligible": True,
            "base_resume_text": "Python",
            "required_skills": ["Python", "SQL"],
            "preferred_skills": ["Airflow"],
        }
    )
    assert out["initial_ats_score"] == 0
    assert "manual review" in out["feedback"].lower()


def test_resume_editor_falls_back_to_base_resume(monkeypatch: pytest.MonkeyPatch):
    from agents import resume_editor as redit

    monkeypatch.setattr(
        redit.model_router,
        "generate_text",
        lambda **kwargs: {"status": "error", "message": "provider_down", "text": ""},
    )

    state = {
        "is_eligible": True,
        "base_resume_text": "BASE RESUME",
        "job_description": "Need Python",
        "missing_skills": ["Python"],
    }
    out = redit.tailor_resume(state)
    assert out["tailored_resume_text"] == "BASE RESUME"


def test_humanize_resume_uses_router_output(monkeypatch: pytest.MonkeyPatch):
    from agents import humanize_resume as hr

    monkeypatch.setenv("CCP_FAST_PIPELINE", "0")
    monkeypatch.setattr(
        hr.model_router,
        "generate_text",
        lambda **kwargs: {"status": "ok", "text": "HUMANIZED"},
    )

    out = hr.humanize_resume({"tailored_resume_text": "x" * 140})
    assert out["humanized_resume_text"] == "HUMANIZED"
