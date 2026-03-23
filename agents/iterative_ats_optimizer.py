"""
Iterative ATS Optimizer - Loop until internal ATS score = 100 or no truthful improvement.
Truth-safe: only adds keywords supported by master resume.
"""

from typing import Callable, Optional, Any
from agents.master_resume_guard import parse_master_resume, get_truthful_missing_keywords
from agents.state import AgentState


DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_TARGET_SCORE = 100


def run_iterative_ats_optimizer(
    state: AgentState,
    ats_checker: Any,
    tailor_fn: Callable,
    humanize_fn: Callable,
    target_score: int = DEFAULT_TARGET_SCORE,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    truth_safe: bool = True,
) -> dict:
    """
    Iterative loop:
    1. Score resume with ATS checker
    2. If score >= target_score -> done
    3. Get missing keywords, filter to truthful only (if truth_safe)
    4. If no truthful improvements -> done
    5. Rewrite from master resume with allowed skills only
    6. Humanize, re-score, repeat
    """
    master_text = state.get("base_resume_text", "")
    master_inventory = parse_master_resume(master_text) if truth_safe else {}

    current_resume = master_text
    current_score = 0
    attempt = 0
    last_feedback = []
    last_missing = []
    last_truthful_missing = []

    def _run_ats_check(resume_text: str) -> dict:
        return ats_checker.comprehensive_ats_check(
            resume_text=resume_text,
            job_description=state.get("job_description", ""),
            job_title=state.get("target_position", ""),
            company_name=state.get("target_company", ""),
            location=state.get("target_location", ""),
        )

    while attempt < max_attempts:
        attempt += 1

        ats_result = _run_ats_check(current_resume)
        current_score = ats_result.get("ats_score", 0)
        last_feedback = ats_result.get("feedback", [])
        if isinstance(last_feedback, str):
            last_feedback = last_feedback.split("\n") if last_feedback else []
        last_missing = ats_result.get("detailed_breakdown", {}).get("missing_keywords", [])

        if current_score >= target_score:
            return {
                "tailored_resume_text": current_resume,
                "humanized_resume_text": current_resume,
                "initial_ats_score": current_score,
                "final_ats_score": current_score,
                "feedback": last_feedback,
                "missing_keywords": last_missing,
                "truthful_missing_keywords": last_truthful_missing,
                "attempts": attempt,
                "converged": True,
            }

        # Truth-safe: only add keywords from master
        if truth_safe and master_inventory:
            last_truthful_missing = get_truthful_missing_keywords(master_inventory, last_missing)
            if not last_truthful_missing:
                return {
                    "tailored_resume_text": current_resume,
                    "humanized_resume_text": current_resume,
                    "initial_ats_score": current_score,
                    "final_ats_score": current_score,
                    "feedback": last_feedback,
                    "missing_keywords": last_missing,
                    "truthful_missing_keywords": [],
                    "attempts": attempt,
                    "converged": False,
                    "no_truthful_improvement": True,
                }
            missing_for_rewrite = last_truthful_missing
        else:
            missing_for_rewrite = last_missing[:10]

        # Rewrite with allowed skills only
        rewrite_state = {
            **state,
            "base_resume_text": current_resume,
            "missing_skills": missing_for_rewrite,
            "allowed_skills": list(master_inventory.get("skills", set()) | master_inventory.get("tools", set())) if truth_safe else None,
        }
        tailor_result = tailor_fn(rewrite_state)
        current_resume = tailor_result.get("tailored_resume_text", current_resume)

        # Humanize
        humanize_state = {**state, "tailored_resume_text": current_resume}
        humanize_result = humanize_fn(humanize_state)
        current_resume = humanize_result.get("humanized_resume_text", current_resume)

    return {
        "tailored_resume_text": current_resume,
        "humanized_resume_text": current_resume,
        "initial_ats_score": current_score,
        "final_ats_score": current_score,
        "feedback": last_feedback,
        "missing_keywords": last_missing,
        "truthful_missing_keywords": last_truthful_missing,
        "attempts": attempt,
        "converged": current_score >= target_score,
    }
