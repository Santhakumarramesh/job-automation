"""
Phase 11 — High-Confidence Discovery Filter
Filters discovered jobs to only surface strong candidates.
Prevents noisy lists of weak-fit jobs from reaching the approval queue.
"""
from __future__ import annotations

from typing import Optional

from services.fit_engine import score_structured_fit, fit_result_to_dict, CANDIDATE_ROLE_FAMILIES, detect_role_family

# Thresholds
MIN_OVERALL_FIT = 60
MIN_ATS_FEASIBILITY = 55
MAX_HARD_BLOCKERS = 0


class JobPrefilterResult:
    HIGH_CONFIDENCE = "high_confidence_match"
    REVIEW_FIT = "review_fit"
    SKIP = "skip"


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
    if family not in CANDIDATE_ROLE_FAMILIES:
        return {
            "classification": JobPrefilterResult.SKIP,
            "reason": f"Role family '{family}' outside candidate specialization",
            "job_url": job_url,
            "job_title": job_title,
            "company": company,
        }

    # Work auth + location check
    jd_lower = job_description.lower()
    work_auth_blockers = ["us citizens only", "us citizens and permanent residents",
                          "no visa sponsorship", "must be authorized to work"]
    has_work_auth_issue = any(p in jd_lower for p in work_auth_blockers)
    visa_status = profile.get("visa_status", "")
    if has_work_auth_issue and "green card" not in visa_status.lower() and "citizen" not in visa_status.lower():
        return {
            "classification": JobPrefilterResult.SKIP,
            "reason": "Work authorization restriction detected for non-citizen/non-PR candidate",
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

    if fit.overall_fit_score >= MIN_OVERALL_FIT and fit.fit_decision == "apply":
        classification = JobPrefilterResult.HIGH_CONFIDENCE
    elif fit.overall_fit_score >= 50 or fit.fit_decision == "review_fit":
        classification = JobPrefilterResult.REVIEW_FIT
    else:
        classification = JobPrefilterResult.SKIP

    return {
        "classification": classification,
        "reason": "; ".join(fit.fit_reasons[:2]),
        "fit": fit_dict,
        "job_url": job_url,
        "job_title": job_title,
        "company": company,
        "location": location,
        "work_type": work_type,
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
        return r.get("fit", {}).get("overall_fit_score", 0)

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
