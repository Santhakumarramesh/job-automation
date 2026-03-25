from __future__ import annotations

import types
from typing import Any, Callable

import pytest

from agents.iterative_ats_optimizer import run_iterative_ats_optimizer


class _DummyATSChecker:
    def __init__(self, scores: list[int], missing_keywords: list[str] | None = None):
        self._scores = scores
        self._missing = missing_keywords or ["X"]
        self._i = 0

    def comprehensive_ats_check(self, *, resume_text: str, **kwargs: Any) -> dict[str, Any]:
        score = self._scores[min(self._i, len(self._scores) - 1)]
        self._i += 1
        return {
            "ats_score": score,
            "feedback": [],
            "detailed_breakdown": {"missing_keywords": list(self._missing)},
        }


def _tailor_fn(_: dict[str, Any]) -> dict[str, Any]:
    # Preserve determinism: "tailoring" just returns the same resume text.
    return {"tailored_resume_text": _.get("base_resume_text", "")}


def _humanize_fn(state: dict[str, Any]) -> dict[str, Any]:
    return {"humanized_resume_text": state.get("tailored_resume_text", "")}


def test_optimizer_structured_output_keys_present():
    # truth_safe=False avoids reliance on master resume parsing helpers.
    checker = _DummyATSChecker(scores=[50, 55, 70])
    out = run_iterative_ats_optimizer(
        state={"base_resume_text": "base", "job_description": "jd", "target_position": "t", "target_company": "c", "target_location": "l"},
        ats_checker=checker,
        tailor_fn=_tailor_fn,
        humanize_fn=_humanize_fn,
        target_score=100,
        max_attempts=3,
        truth_safe=False,
        min_score_gain_delta=2,
    )
    assert out["baseline_score"] == out["initial_ats_score"]
    assert out["final_internal_ats_score"] == out["final_ats_score"]
    assert "truthful_ceiling" in out
    assert out["iterations"] == out["attempts"]
    assert out["ats_oriented_resume_text"] == out["tailored_resume_text"]
    assert out["human_readable_resume_text"] == out["humanized_resume_text"]
    assert "humanized_resume_text" in out
    assert "tailored_resume_text" in out


def test_optimizer_early_stop_when_score_gain_small(monkeypatch: pytest.MonkeyPatch):
    checker = _DummyATSChecker(scores=[50, 50, 50], missing_keywords=["X"])

    out = run_iterative_ats_optimizer(
        state={"base_resume_text": "base", "job_description": "jd", "target_position": "t", "target_company": "c", "target_location": "l"},
        ats_checker=checker,
        tailor_fn=_tailor_fn,
        humanize_fn=_humanize_fn,
        target_score=100,
        max_attempts=5,
        truth_safe=False,
        min_score_gain_delta=1,
    )
    assert out["stopped_early"] is True
    assert out["score_gain"] == 0
    assert out["iterations"] >= 2


def test_optimizer_no_truthful_improvement_path_sets_flags(monkeypatch: pytest.MonkeyPatch):
    # Simulate truth_safe=True but no truthful improvements by patching helper functions.
    from agents import iterative_ats_optimizer as mod

    class _Inv:
        def allowed_skills_list(self):
            return []

    monkeypatch.setattr(mod, "parse_master_resume", lambda _: _Inv())
    monkeypatch.setattr(mod, "get_truthful_missing_keywords", lambda _inv, _missing: [])

    checker = _DummyATSChecker(scores=[50, 60], missing_keywords=["X"])
    out = run_iterative_ats_optimizer(
        state={"base_resume_text": "base", "job_description": "jd", "target_position": "t", "target_company": "c", "target_location": "l"},
        ats_checker=checker,
        tailor_fn=_tailor_fn,
        humanize_fn=_humanize_fn,
        target_score=100,
        max_attempts=5,
        truth_safe=True,
        min_score_gain_delta=0,
    )
    assert out.get("no_truthful_improvement") is True
    assert out["truthful_ceiling"] == out["final_internal_ats_score"]

