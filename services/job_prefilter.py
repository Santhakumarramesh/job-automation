"""
Phase 3 — High-Confidence Discovery Filter
Filters discovered jobs to only surface strong candidates.
Prevents noisy lists of weak-fit jobs from reaching the approval queue.
"""
from __future__ import annotations

import re
from typing import Optional

from services.fit_engine import (
    CANDIDATE_ROLE_FAMILIES,
    detect_role_family,
    infer_candidate_role_families,
    fit_result_to_dict,
    score_structured_fit,
)
from services.job_location_match import job_is_remoteish, job_location_haystack, haystack_matches_region

# Thresholds
MIN_OVERALL_FIT = 60
MIN_SENIORITY_MATCH = 50
MIN_ATS_FEASIBILITY = 55
MAX_HARD_BLOCKERS = 0


class JobPrefilterResult:
    HIGH_CONFIDENCE = "high_confidence_match"
    REVIEW_FIT = "review_fit"
    SKIP = "skip"


def _profile_allows_remote(profile: dict) -> bool:
    if profile.get("open_to_remote") is False:
        return False
    locs = profile.get("application_locations") or []
    for loc in locs:
        if isinstance(loc, dict) and loc.get("remote_ok") is True:
            return True
    return profile.get("open_to_remote", True)


def _location_compatible(job: dict, profile: dict) -> tuple[bool, str]:
    profile = profile or {}
    app_locs = profile.get("application_locations") or []
    preferred = profile.get("preferred_locations") or []
    if not app_locs and not preferred:
        return True, ""

    hay = job_location_haystack(job)
    if not hay.strip():
        return False, "Job location missing"

    if job_is_remoteish(job) and _profile_allows_remote(profile):
        return True, ""

    tokens: list[str] = []
    for raw in app_locs:
        if not isinstance(raw, dict):
            continue
        for key in ("label", "city", "state_region", "country"):
            v = str(raw.get(key) or "").strip()
            if len(v) >= 2:
                tokens.append(v)
    tokens.extend([str(p) for p in preferred if str(p).strip()])

    for tok in tokens:
        if haystack_matches_region(hay, tok):
            return True, ""

    return False, "Location outside candidate preferences"


def _work_auth_compatible(job_description: str, profile: dict) -> tuple[bool, str]:
    jd_lower = (job_description or "").lower()
    visa_status = str(profile.get("visa_status", "")).lower()
    work_note = str(profile.get("work_authorization_note", "")).lower()
    citizenship_ok = any(x in visa_status or x in work_note for x in ["citizen", "green card", "permanent resident"])

    if re.search(r"\bus citizens? only\b|\bcitizenship required\b|\bmust be a us citizen\b", jd_lower):
        if not citizenship_ok:
            return False, "US citizenship required"

    if "no sponsorship" in jd_lower or "without sponsorship" in jd_lower:
        requires_sponsorship = any(k in visa_status for k in ["opt", "h1b", "sponsor", "student"]) and not citizenship_ok
        if requires_sponsorship:
            return False, "No visa sponsorship"

    return True, ""


def prefilter_job(
    job_url: str,
    job_title: str,
    company: str,
    job_description: str,
    location: str,
    work_type: str,
    resume_text: str,
    profile: Optional[dict] = None,
    ats_score: int = 0,
) -> dict:
    """
    Evaluate a single discovered job for prefilter classification.
    Returns classification + fit data.
    """
    profile = profile or {}

    # Role family check (quick gate)
    family = detect_role_family(job_title, job_description)
    candidate_families = infer_candidate_role_families(resume_text, profile)
    if not candidate_families:
        candidate_families = list(CANDIDATE_ROLE_FAMILIES)
    if family not in candidate_families:
        return {
            "classification": JobPrefilterResult.SKIP,
            "reason": f"Role family '{family}' outside candidate specialization",
            "job_url": job_url,
            "job_title": job_title,
            "company": company,
        }

    # Location compatibility
    loc_ok, loc_reason = _location_compatible(
        {
            "location": location,
            "work_type": work_type,
            "title": job_title,
            "description": job_description,
        },
        profile,
    )
    if not loc_ok:
        return {
            "classification": JobPrefilterResult.SKIP,
            "reason": loc_reason,
            "job_url": job_url,
            "job_title": job_title,
            "company": company,
        }

    # Work authorization compatibility (pre-fit safety gate)
    auth_ok, auth_reason = _work_auth_compatible(job_description, profile)
    if not auth_ok:
        return {
            "classification": JobPrefilterResult.SKIP,
            "reason": auth_reason,
            "job_url": job_url,
            "job_title": job_title,
            "company": company,
        }

    # Structured fit score
    fit = score_structured_fit(job_title, job_description, resume_text, profile, ats_score)
    fit_dict = fit_result_to_dict(fit)

    if fit.hard_blockers:
        return {
            "classification": JobPrefilterResult.SKIP,
            "reason": f"Hard blockers: {'; '.join(fit.hard_blockers)}",
            "fit": fit_dict,
            "job_url": job_url,
            "job_title": job_title,
            "company": company,
        }

    # ATS feasibility check (prefit or actual ATS)
    ats_feasible = ats_score <= 0 or int(ats_score) >= MIN_ATS_FEASIBILITY

    if (
        fit.overall_fit_score >= MIN_OVERALL_FIT
        and fit.fit_decision == "apply"
        and fit.seniority_match_score >= MIN_SENIORITY_MATCH
        and ats_feasible
    ):
        classification = JobPrefilterResult.HIGH_CONFIDENCE
    elif fit.overall_fit_score >= 50 or fit.fit_decision == "review_fit":
        classification = JobPrefilterResult.REVIEW_FIT
    else:
        classification = JobPrefilterResult.SKIP

    reason_bits = list(fit.fit_reasons[:2])
    if fit.seniority_match_score < MIN_SENIORITY_MATCH:
        reason_bits.append("Seniority mismatch")
    if not ats_feasible and int(ats_score or 0) > 0:
        reason_bits.append("ATS feasibility below threshold")

    return {
        "classification": classification,
        "reason": "; ".join(reason_bits),
        "fit": fit_dict,
        "job_url": job_url,
        "job_title": job_title,
        "company": company,
        "location": location,
        "work_type": work_type,
        "ats_feasible": ats_feasible,
        "ats_feasibility_score": ats_score,
    }


def prefilter_batch(
    jobs: list[dict],
    resume_text: str,
    profile: Optional[dict] = None,
    ats_scores: Optional[dict] = None,
) -> dict:
    """
    Prefilter a batch of jobs.
    jobs: list of {url, title, company, description, location, work_type}
    Returns {high_confidence, review_fit, skip, total}
    """
    ats_scores = ats_scores or {}
    profile = profile or {}

    high_confidence = []
    review_fit = []
    skip = []

    for job in jobs:
        url = job.get("url", job.get("job_url", ""))
        title = job.get("title", job.get("job_title", ""))
        company = job.get("company", "")
        description = job.get("description", job.get("job_description", ""))
        location = job.get("location", "")
        work_type = job.get("work_type", "remote")
        ats_score = ats_scores.get(url, 0)

        result = prefilter_job(
            job_url=url,
            job_title=title,
            company=company,
            job_description=description,
            location=location,
            work_type=work_type,
            resume_text=resume_text,
            profile=profile,
            ats_score=ats_score,
        )

        if result["classification"] == JobPrefilterResult.HIGH_CONFIDENCE:
            high_confidence.append(result)
        elif result["classification"] == JobPrefilterResult.REVIEW_FIT:
            review_fit.append(result)
        else:
            skip.append(result)

    # Sort by fit score
    def _sort_key(r):
        fit = r.get("fit", {}) or {}
        return (
            fit.get("overall_fit_score", 0),
            fit.get("seniority_match_score", 0),
            fit.get("role_match_score", 0),
        )

    high_confidence.sort(key=_sort_key, reverse=True)
    review_fit.sort(key=_sort_key, reverse=True)

    return {
        "high_confidence": high_confidence,
        "review_fit": review_fit,
        "skip": skip,
        "total": len(jobs),
        "high_confidence_count": len(high_confidence),
        "review_fit_count": len(review_fit),
        "skip_count": len(skip),
    }
