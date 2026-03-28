from __future__ import annotations

import pytest


def test_project_generator_uses_router(monkeypatch: pytest.MonkeyPatch):
    from agents import project_generator as pg

    monkeypatch.setattr(
        pg.model_router,
        "generate_text",
        lambda **kwargs: {"status": "ok", "text": "Project Title: RAG Ops"},
    )

    out = pg.generate_project(
        {
            "is_eligible": True,
            "missing_skills": ["RAG", "LangChain"],
            "target_position": "ML Engineer",
            "target_company": "ExampleCo",
            "job_description": "Need RAG and LLM ops",
        }
    )
    assert out["generated_project_text"].startswith("Project Title")


def test_interview_prep_router_fallback(monkeypatch: pytest.MonkeyPatch):
    from agents import interview_prep_agent as ipa

    monkeypatch.setattr(ipa, "get_company_info", lambda company: "About company")
    monkeypatch.setattr(
        ipa.model_router,
        "generate_text",
        lambda **kwargs: {"status": "error", "message": "provider_down", "text": ""},
    )

    out = ipa.generate_interview_prep("JD text", "Resume text", "ExampleCo")
    assert "Failed to generate" in out


def test_intelligent_project_generator_uses_router(monkeypatch: pytest.MonkeyPatch):
    from agents import intelligent_project_generator as ipg

    def _fake_generate_json(**kwargs):
        prompt = kwargs.get("prompt", "")
        if "Extract the skills" in prompt and "Job description" not in prompt:
            if "python sql airflow" in prompt.lower():
                return {"status": "ok", "data": {"skills": ["Python", "SQL", "Airflow"]}}
            return {"status": "ok", "data": {"skills": ["Python", "SQL"]}}
        return {"status": "ok", "data": {"skills": ["Python", "SQL", "Airflow"]}}

    monkeypatch.setattr(ipg.model_router, "generate_json", _fake_generate_json)
    monkeypatch.setattr(
        ipg.model_router,
        "generate_text",
        lambda **kwargs: {"status": "ok", "text": "Build a fast Airflow ETL pipeline demo."},
    )

    out = ipg.intelligent_project_generator(
        {
            "job_description": "Python SQL Airflow",
            "base_resume_text": "Python SQL",
        }
    )
    assert "Airflow" in out["generated_project_text"]
