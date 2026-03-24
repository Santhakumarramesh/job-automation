"""Application answerer structured output (manual_review_required)."""

from agents.application_answerer import (
    REASON_EMPTY,
    REASON_GENERIC_LLM,
    REASON_MISSING_SPONSORSHIP,
    answer_batch,
    answer_question,
    answer_question_structured,
)


def test_answer_question_backward_compat_string():
    profile = {
        "full_name": "A B",
        "work_authorization_note": "Authorized to work in the US; no sponsorship required.",
        "short_answers": {},
    }
    s = answer_question("Do you require visa sponsorship?", profile=profile)
    assert "sponsorship" in s.lower() or "authorized" in s.lower() or "no" in s.lower()


def test_structured_sponsorship_missing_flags_review():
    profile = {"short_answers": {}}
    r = answer_question_structured("Do you require sponsorship?", profile=profile)
    assert r["manual_review_required"] is True
    assert REASON_MISSING_SPONSORSHIP in r["reason_codes"]
    assert r["classified_type"] == "sponsorship"


def test_structured_relocation_empty():
    r = answer_question_structured("Are you willing to relocate?", profile={})
    assert r["manual_review_required"] is True
    assert REASON_EMPTY in r["reason_codes"]
    assert r["answer"] == ""


def test_structured_generic_llm_flags_review(monkeypatch):
    profile = {"full_name": "X", "email": "x@y.com"}
    import agents.application_answerer as aa

    monkeypatch.setattr(aa, "_answer_generic_llm", lambda *a, **k: "Short truthful line.")
    r = answer_question_structured(
        "What makes you unique for this team?",
        question_type="generic",
        profile=profile,
        use_llm=True,
    )
    assert r["manual_review_required"] is True
    assert REASON_GENERIC_LLM in r["reason_codes"]
    assert r["answer"]


def test_answer_batch_shape():
    profile = {"relocation_preference": "Remote only"}
    items = answer_batch(
        [{"text": "Work location preference?"}],
        profile,
        use_llm=False,
    )
    assert len(items) == 1
    assert "question" in items[0]
    assert "manual_review_required" in items[0]
    assert items[0]["classified_type"] == "relocation"
