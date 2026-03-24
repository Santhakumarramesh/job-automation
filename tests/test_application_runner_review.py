"""Application runner + answerer_structured review metadata."""

from agents.application_runner import (
    RunConfig,
    answerer_review_pending,
    _get_value_and_meta_for_field,
)


def test_answerer_review_pending():
    assert answerer_review_pending({}) is False
    assert answerer_review_pending({"f": {"manual_review_required": False}}) is False
    assert answerer_review_pending({"f": {"manual_review_required": True}}) is True


def test_get_value_meta_answerer_flags_empty_profile():
    job = {"company": "Co", "title": "Dev", "description": ""}
    cfg = RunConfig(profile={}, use_answerer=True)
    val, meta = _get_value_and_meta_for_field(
        "visa sponsorship required?",
        "sponsor",
        cfg,
        job,
    )
    assert "review" in val.lower() or val == ""
    assert meta is not None
    assert meta.get("manual_review_required") is True
    assert meta.get("classified_type") == "sponsorship"


def test_get_value_meta_profile_no_review():
    job = {"company": "Co", "title": "Dev"}
    cfg = RunConfig(
        profile={"full_name": "Jane Q Doe", "email": "j@e.com"},
        use_answerer=True,
    )
    val, meta = _get_value_and_meta_for_field("first name", "firstName", cfg, job)
    assert val == "Jane"
    assert meta is None
