"""
Apify job provider. Uses AI Deep Job Search actor.
"""

from datetime import datetime
from typing import Optional
from apify_client import ApifyClient

from providers.common_schema import JobListing, normalize_to_schema
from providers.base_provider import JobProvider, SearchFilters


def fetch_apify_jobs(
    apify_api_key: str,
    job_titles: list[str],
    locations: list[str],
    skills: list[str],
    max_results: int = 50,
    resume_context: str = "",
) -> list[JobListing]:
    """
    Fetch jobs from Apify AI Deep Job Search.
    Returns normalized JobListing list.
    """
    if not apify_api_key:
        return []

    client = ApifyClient(apify_api_key)
    run_input = {
        "target_job_titles": job_titles[:3],
        "locations": locations[:3],
        "preferred_skills": skills[:10],
        "undesirable_skills": [],
        "preferred_industries": ["Technology", "AI/ML", "Software"],
        "undesirable_industries": ["Defense", "Tobacco"],
        "experience_levels": ["Mid-level", "Senior", "Lead"],
        "max_results": max_results,
        "additional_requirements": resume_context[:500] if resume_context else "",
    }

    try:
        run = client.actor("jobo.world/ai-deep-job-search").call(run_input=run_input)
        dataset = client.dataset(run["defaultDatasetId"])
        items = list(dataset.iterate_items())
    except Exception as e:
        print(f"Apify fetch error: {e}")
        return []

    jobs = []
    for i, item in enumerate(items):
        row = {
            "title": item.get("title") or item.get("jobTitle") or item.get("position"),
            "company": item.get("company") or item.get("companyName"),
            "location": item.get("location") or item.get("locationName") or item.get("place"),
            "description": item.get("description") or item.get("jobDescription") or item.get("details", ""),
            "url": item.get("url") or item.get("link") or item.get("jobUrl") or item.get("applyUrl", ""),
            "job_id": item.get("id") or item.get("jobId") or str(i),
            "apply_url": item.get("applyUrl") or item.get("apply_url", ""),
        }
        jobs.append(normalize_to_schema(row, "apify"))
    return jobs


class ApifyProvider(JobProvider):
    """Apify AI Deep Job Search implementation of JobProvider."""

    def __init__(self, apify_api_key: str):
        self.apify_api_key = apify_api_key or ""

    @property
    def provider_id(self) -> str:
        return "apify"

    def search(
        self,
        keywords: list[str],
        location: str,
        filters: SearchFilters,
        max_results: int,
    ) -> list[JobListing]:
        # Apify actor uses job_titles, locations, skills; map keywords
        job_titles = keywords[:3] if keywords else ["AI/ML Engineer", "Machine Learning Engineer"]
        locations = [location] if location else ["USA", "Remote"]
        skills = keywords[3:13] if len(keywords) > 3 else ["Python", "Machine Learning", "AI"]
        return fetch_apify_jobs(
            self.apify_api_key,
            job_titles=job_titles,
            locations=locations,
            skills=skills,
            max_results=max_results,
        )

    def get_job_details(self, job_id: str) -> Optional[JobListing]:
        # Apify doesn't support fetch-by-id; return None
        return None
