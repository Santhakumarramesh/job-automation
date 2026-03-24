"""
Job provider registry. Fetches from Apify, LinkedIn MCP, or both.
Uses unified JobListing schema and SearchFilters.
"""

from datetime import datetime
from typing import Literal, Optional

import pandas as pd

from providers.common_schema import JobListing, jobs_to_dataframe
from providers.base_provider import JobProvider, SearchFilters
from providers.apify_jobs import fetch_apify_jobs, ApifyProvider
from providers.linkedin_mcp_jobs import fetch_linkedin_mcp_jobs, LinkedInMCPProvider
from services.prefit_ranker import add_prefit_scores_to_dataframe, prefit_keyword_bundle

ProviderChoice = Literal["apify", "linkedin_mcp", "both"]


def get_jobs(
    provider: ProviderChoice,
    resume_text: str,
    apify_api_key: str = "",
    max_results: int = 50,
    filters: Optional[SearchFilters] = None,
) -> tuple[pd.DataFrame, list[JobListing]]:
    """
    Fetch jobs from selected provider(s). Returns (DataFrame, raw JobListing list).
    DataFrame has resume_match_score for UI; raw list for further processing.
    filters: optional SearchFilters for date_posted, job_type, experience_level, easy_apply, etc.
    """
    filters = filters or SearchFilters()
    kw = prefit_keyword_bundle(resume_text)
    jobs: list[JobListing] = []
    resume_ctx = (resume_text or "")[:500]
    keywords = kw["job_titles"][:2] + kw["skills"][:3]
    location = kw["locations"][0] if kw["locations"] else "United States"

    if provider in ("apify", "both") and apify_api_key:
        apify_jobs = fetch_apify_jobs(
            apify_api_key,
            job_titles=kw["job_titles"],
            locations=kw["locations"],
            skills=kw["skills"],
            max_results=max_results if provider == "apify" else max_results // 2,
            resume_context=resume_ctx,
        )
        jobs.extend(apify_jobs)

    if provider in ("linkedin_mcp", "both"):
        linkedin_jobs = fetch_linkedin_mcp_jobs(
            keywords=keywords,
            location=location,
            work_type=filters.work_remote or "remote",
            max_results=max_results if provider == "linkedin_mcp" else max_results // 2,
            easy_apply=filters.easy_apply,
            date_posted=filters.date_posted,
            job_type=filters.job_type,
            experience_level=filters.experience_level,
            sort_order=filters.sort_order,
        )
        jobs.extend(linkedin_jobs)

    if not jobs:
        return pd.DataFrame(), []

    # Compute apply_mode + policy_reason (central policy; profile gates auto-apply)
    try:
        from services.policy_service import decide_apply_mode_with_reason
        from services.profile_service import load_profile, is_auto_apply_ready

        prof = load_profile()
        profile_ready = is_auto_apply_ready(prof)
        for j in jobs:
            apply_u = (j.apply_url or "").strip()
            job_dict = {
                "url": j.url,
                "apply_url": apply_u,
                "easy_apply_confirmed": j.easy_apply_confirmed,
                "location": j.location,
                "title": j.title,
                "work_type": j.work_type,
                "description": (j.description or "")[:800],
            }
            mode, reason = decide_apply_mode_with_reason(
                job_dict, profile_ready=profile_ready, profile=prof
            )
            j.apply_mode = mode
            j.policy_reason = reason
    except ImportError:
        pass

    df = jobs_to_dataframe(jobs)
    df["search_date"] = datetime.now()
    df = add_prefit_scores_to_dataframe(df, keyword_bundle=kw)
    return df, jobs


def get_provider(provider_id: str, apify_api_key: str = "") -> Optional[JobProvider]:
    """Get a JobProvider instance by id."""
    if provider_id == "apify":
        return ApifyProvider(apify_api_key)
    if provider_id == "linkedin_mcp":
        return LinkedInMCPProvider()
    return None


def list_providers() -> list[dict]:
    """Return available providers and their status."""
    return [
        {"id": "apify", "name": "Apify (AI Deep Job Search)", "needs_key": True},
        {"id": "linkedin_mcp", "name": "LinkedIn MCP", "needs_key": False},
        {"id": "both", "name": "Apify + LinkedIn MCP", "needs_key": True},
    ]
