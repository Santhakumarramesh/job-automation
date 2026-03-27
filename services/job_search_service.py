"""
Job search service. get_jobs(provider, filters), uses registry.
"""

import pandas as pd
from typing import Optional

from services.enhanced_job_finder import EnhancedJobFinder
from providers.base_provider import SearchFilters
from services.discovery_ranker import annotate_dataframe_with_prefilter, rank_discovery_results


def get_jobs(
    resume_text: str,
    provider: str = "apify",
    apify_api_key: str = "",
    max_results: int = 50,
    filters: Optional[SearchFilters] = None,
    prefilter: bool = True,
    include_review: bool = True,
    profile: Optional[dict] = None,
) -> pd.DataFrame:
    """
    Find jobs via Apify, LinkedIn MCP, or both.
    Returns DataFrame with title, company, location, description, url, etc.
    When prefilter=True (default), hides weak-fit jobs and annotates prefilter columns.
    """
    finder = EnhancedJobFinder(apify_api_key or "", provider=provider)
    df = finder.find_jobs(resume_text, max_results=max_results, filters=filters)
    if df is None or df.empty or not prefilter:
        return df

    jobs = []
    for row in df.to_dict(orient="records"):
        jobs.append(
            {
                "url": row.get("url") or row.get("job_url") or "",
                "title": row.get("title") or row.get("job_title") or row.get("position") or "",
                "company": row.get("company") or row.get("company_name") or "",
                "description": row.get("description") or row.get("job_description") or "",
                "location": row.get("location") or row.get("locationName") or "",
                "work_type": row.get("work_type") or row.get("workType") or "remote",
            }
        )

    ats_scores = {}
    if "resume_match_score" in df.columns:
        for row in df.to_dict(orient="records"):
            url = row.get("url") or row.get("job_url") or ""
            if url:
                ats_scores[url] = int(row.get("resume_match_score") or 0)

    if profile is None:
        try:
            from services.profile_service import load_profile

            profile = load_profile() or {}
        except Exception:
            profile = {}

    prefilter_result = rank_discovery_results(
        jobs,
        resume_text=resume_text or "",
        profile=profile,
        ats_scores=ats_scores,
    )
    return annotate_dataframe_with_prefilter(df, prefilter_result, include_review=include_review)


def search_jobs_payload(
    *,
    keywords: str,
    location: str = "United States",
    max_results: int = 25,
    easy_apply: bool = False,
    include_prefilter: bool = False,
) -> dict:
    """
    MCP/REST search helper for LinkedIn MCP. Returns {status, count, jobs, prefilter?}.
    """
    from providers.linkedin_mcp_jobs import linkedin_mcp_search_jobs_payload

    result = linkedin_mcp_search_jobs_payload(
        keywords=keywords,
        location=location or "United States",
        work_type="remote" if "remote" in (location or "").lower() else "",
        max_results=max_results,
        easy_apply=easy_apply,
    )

    if not include_prefilter or result.get("status") != "ok":
        return result

    try:
        from services.resume_package_service import _load_master_resume_text
        from services.profile_service import load_profile

        resume_text = _load_master_resume_text()
        profile = load_profile() or {}
        jobs = result.get("jobs", []) or []
        normalized = []
        for j in jobs:
            normalized.append(
                {
                    "url": j.get("url") or j.get("job_url") or j.get("apply_url") or "",
                    "title": j.get("title") or j.get("job_title") or "",
                    "company": j.get("company") or "",
                    "description": j.get("description") or j.get("job_description") or "",
                    "location": j.get("location") or "",
                    "work_type": j.get("work_type") or "remote",
                }
            )
        prefilter_result = rank_discovery_results(
            normalized,
            resume_text=resume_text,
            profile=profile,
        )
        result["prefilter"] = prefilter_result
    except Exception as e:
        result["prefilter_error"] = str(e)[:160]

    return result
