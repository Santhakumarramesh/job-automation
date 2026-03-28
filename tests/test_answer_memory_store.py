from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def memory_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "answer_memory.db"
    monkeypatch.setenv("ANSWER_MEMORY_DB_PATH", str(db_path))
    yield db_path


def test_save_and_get_answer(memory_db: Path):
    from services.answer_memory_store import save_approved_answer, get_saved_answer

    save_approved_answer(
        question_text="Do you require sponsorship?",
        approved_answer="No, I do not require sponsorship.",
        context={"country": "US", "role_family": "ai_ml_engineer"},
        answer_state="safe",
        approved_by="user1",
        auto_use_allowed=True,
    )

    res = get_saved_answer(
        question_text="Do you require sponsorship?",
        job_context={"country": "US", "role_family": "ai_ml_engineer"},
        require_context_match=True,
    )
    assert res["found"] is True
    assert res["answer_state"] == "safe"
    assert res["context_match"] is True


def test_context_mismatch_blocks_auto_use(memory_db: Path):
    from services.answer_memory_store import save_approved_answer, get_saved_answer

    save_approved_answer(
        question_text="Are you authorized to work in the US?",
        approved_answer="Yes, authorized to work in the US.",
        context={"country": "US"},
        answer_state="safe",
        approved_by="user1",
        auto_use_allowed=True,
    )

    res = get_saved_answer(
        question_text="Are you authorized to work in the US?",
        job_context={"country": "CA"},
        require_context_match=True,
    )
    assert res["found"] is False


def test_mark_answer_requires_review(memory_db: Path):
    from services.answer_memory_store import save_approved_answer, get_saved_answer, mark_answer_requires_review

    save_approved_answer(
        question_text="What is your notice period?",
        approved_answer="2 weeks",
        answer_state="safe",
        auto_use_allowed=True,
    )
    assert mark_answer_requires_review("notice_period") is True
    res = get_saved_answer(question_text="What is your notice period?")
    assert res["found"] is True
    assert res["answer_state"] == "review"
    assert res["auto_use_allowed"] is False
