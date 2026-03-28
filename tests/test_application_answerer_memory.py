from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def memory_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "answer_memory.db"
    monkeypatch.setenv("ANSWER_MEMORY_DB_PATH", str(db_path))
    yield db_path


def test_answerer_uses_memory_when_safe(memory_db: Path):
    from services.answer_memory_store import save_approved_answer
    from agents.application_answerer import answer_question_structured

    save_approved_answer(
        question_text="Do you require sponsorship?",
        approved_answer="No, I do not require sponsorship.",
        answer_state="safe",
        auto_use_allowed=True,
    )

    out = answer_question_structured(
        question_text="Do you require sponsorship?",
        profile={},
        master_resume_text="",
        job_context={"company": "ExampleCo", "title": "ML Engineer"},
        use_llm=False,
    )
    assert out["answer"] == "No, I do not require sponsorship."
    assert out["manual_review_required"] is False


def test_answerer_requires_review_when_memory_not_safe(memory_db: Path):
    from services.answer_memory_store import save_approved_answer
    from agents.application_answerer import answer_question_structured

    save_approved_answer(
        question_text="What is your expected salary?",
        approved_answer="$120k",
        answer_state="review",
        auto_use_allowed=False,
    )

    out = answer_question_structured(
        question_text="What is your expected salary?",
        profile={},
        master_resume_text="",
        job_context={},
        use_llm=False,
    )
    assert out["manual_review_required"] is True


def test_generic_answer_uses_router_json_contract(monkeypatch: pytest.MonkeyPatch):
    from agents import application_answerer as aa

    def _fake_generate_json(**kwargs):
        return {
            "status": "ok",
            "data": {
                "answer": "I focus on measurable impact and truthful communication.",
                "manual_review_required": True,
                "reason_codes": ["generic_llm_answer"],
            },
        }

    monkeypatch.setattr(aa.model_router, "generate_json", _fake_generate_json)

    out = aa.answer_question_structured(
        question_text="Tell us anything else relevant to this application.",
        question_type="generic",
        profile={},
        master_resume_text="",
        job_description="",
        job_context={},
        use_llm=True,
    )
    assert out["answer"].startswith("I focus on measurable impact")
    assert out["manual_review_required"] is True
    assert "generic_llm_answer" in out["reason_codes"]
