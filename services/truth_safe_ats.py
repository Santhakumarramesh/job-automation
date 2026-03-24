"""
Truth-safe internal ATS ceiling — estimated max score without fabricating skills or
claiming unsupported JD requirements. Used by MCP, iterative optimizer, and UI.
"""

from __future__ import annotations

from typing import Any, List, Optional


def compute_truth_safe_ats_ceiling(
    final_ats_score: int,
    *,
    target_score: int = 100,
    truth_safe: bool = True,
    converged: bool = False,
    no_truthful_improvement: bool = False,
    stopped_after_max_attempts: bool = False,
    unsupported_requirements: Optional[List[Any]] = None,
    truthful_missing_keywords: Optional[List[Any]] = None,
    initial_ats_score: Optional[int] = None,
) -> dict[str, Any]:
    """
    Return ``truth_safe_ats_ceiling`` (0–100), human ``truth_safe_ceiling_reason``,
    and ``ceiling_limited_by`` tags for audit/UI.

    This is an **internal** estimate for alignment with the JD given the master resume;
    it is not a guarantee for any employer ATS.
    """
    unsup = [str(x).strip() for x in (unsupported_requirements or []) if str(x).strip()]
    truthful_left = [str(x).strip() for x in (truthful_missing_keywords or []) if str(x).strip()]
    final_ats_score = int(max(0, min(100, final_ats_score)))
    target_score = int(max(0, min(100, target_score)))

    if not truth_safe:
        return {
            "truth_safe_ats_ceiling": target_score,
            "truth_safe_ceiling_reason": (
                "Truth-safe mode is off; internal ATS target is not capped by resume inventory."
            ),
            "ceiling_limited_by": [],
        }

    if unsup:
        return {
            "truth_safe_ats_ceiling": final_ats_score,
            "truth_safe_ceiling_reason": (
                "Unsupported job requirements detected for your resume; do not inflate internal ATS "
                "by adding claims outside your master resume. Treat the current score as the safe ceiling "
                "for honest alignment with this posting."
            ),
            "ceiling_limited_by": ["unsupported_requirements"],
        }

    if converged or final_ats_score >= target_score:
        return {
            "truth_safe_ats_ceiling": final_ats_score,
            "truth_safe_ceiling_reason": (
                f"Met or exceeded the internal ATS target ({target_score}%) using truthful wording."
            ),
            "ceiling_limited_by": [],
        }

    if no_truthful_improvement:
        return {
            "truth_safe_ats_ceiling": final_ats_score,
            "truth_safe_ceiling_reason": (
                "No remaining JD keyword gaps are supportable from your master resume inventory; "
                "this is the practical truth-safe ceiling for this job unless you expand your resume truthfully."
            ),
            "ceiling_limited_by": ["truth_inventory"],
        }

    if stopped_after_max_attempts and truthful_left:
        gap = target_score - final_ats_score
        bump = min(gap, min(25, 3 * min(len(truthful_left), 10)))
        est = min(100, final_ats_score + max(bump, 0))
        return {
            "truth_safe_ats_ceiling": est,
            "truth_safe_ceiling_reason": (
                f"Optimizer stopped before target; roughly {len(truthful_left)} inventory-backed keyword(s) "
                f"could still strengthen alignment — estimated truthful ceiling ≈ {est}% "
                f"(re-run with more attempts or manual edits)."
            ),
            "ceiling_limited_by": ["optimizer_attempts"],
        }

    if truthful_left:
        gap = target_score - final_ats_score
        bump = min(gap, min(20, 4 * min(len(truthful_left), 8)))
        est = min(100, final_ats_score + max(bump, 0))
        return {
            "truth_safe_ats_ceiling": est,
            "truth_safe_ceiling_reason": (
                f"Inventory-backed terms still match JD gaps; estimated max truthful internal ATS ≈ {est}% "
                f"if those keywords are woven in without overstating experience."
            ),
            "ceiling_limited_by": ["truth_headroom_estimate"],
        }

    init = initial_ats_score if initial_ats_score is not None else final_ats_score
    return {
        "truth_safe_ats_ceiling": final_ats_score,
        "truth_safe_ceiling_reason": (
            f"Internal ATS is {final_ats_score}% (started at {init}%); no extra truthful keyword headroom "
            "was identified for this pass."
        ),
        "ceiling_limited_by": [],
    }
