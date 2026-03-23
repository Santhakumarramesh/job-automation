"""
Job provider registry. Fetches from Apify, LinkedIn MCP, or both.
"""

from datetime import datetime
from typing import Literal

import pandas as pd

from providers.common_schema import JobListing, jobs_to_dataframe
from providers.apify_jobs import fetch_apify_jobs
from providers.linkedin_mcp_jobs import fetch_linkedin_mcp_jobs

ProviderChoice = Literal["apify", "linkedin_mcp", "both"]


def _analyze_resume_keywords(resume_text: str) -> dict:
    """Extract job titles, locations, skills from resume."""
    text = (resume_text or "").lower()
    kw = {
        "job_titles": [],
        "locations": ["USA", "Remote"],
        "skills": [],
    }
    if "engineer" in text or "ml" in text or "ai" in text:
        kw["job_titles"].extend(["AI Engineer", "Machine Learning Engineer", "Software Engineer"])
    if "data scientist" in text or "data science" in text:
        kw["job_titles"].append("Data Scientist")
    for s in ["Python", "Machine Learning", "AI", "TensorFlow", "PyTorch", "SQL", "AWS", "Docker"]:
        if s.lower() in text:
            kw["skills"].append(s)
    if not kw["job_titles"]:
        kw["job_titles"] = ["AI/ML Engineer", "Machine Learning Engineer", "Data Scientist"]
    if not kw["skills"]:
        kw["skills"] = ["Python", "Machine Learning", "AI"]
    return kw


def get_jobs(
    provider: ProviderChoice,
    resume_text: str,
    apify_api_key: str = "",
    max_results: int = 50,
) -> tuple[pd.DataFrame, list[JobListing]]:
    """
    Fetch jobs from selected provider(s). Returns (DataFrame, raw JobListing list).
    DataFrame has resume_match_score for UI; raw list for further processing.
    """
    kw = _analyze_resume_keywords(resume_text)
    jobs: list[JobListing] = []
    resume_ctx = (resume_text or "")[:500]

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
        keywords = " ".join(kw["job_titles"][:2] + kw["skills"][:3])
        linkedin_jobs = fetch_linkedin_mcp_jobs(
            keywords=keywords,
            location=kw["locations"][0] if kw["locations"] else "United States",
            work_type="remote",
            max_results=max_results if provider == "linkedin_mcp" else max_results // 2,
        )
        jobs.extend(linkedin_jobs)

    if not jobs:
        return pd.DataFrame(), []

    df = jobs_to_dataframe(jobs)
    df["resume_match_score"] = [_match_score(j, kw) for j in jobs]
    df["search_date"] = datetime.now()
    df = df.sort_values("resume_match_score", ascending=False)
    return df, jobs


def _match_score(job: JobListing, kw: dict) -> int:
    """Simple resume match score 0-100."""
    score = 0
    title = job.title.lower()
    desc = job.description.lower()
    loc = job.location.lower()
    for t in kw["job_titles"]:
        if t.lower() in title or t.lower() in desc:
            score += 30
            break
    for s in kw["skills"]:
        if s.lower() in desc:
            score += 8
    for l in kw["locations"]:
        if l.lower() in loc:
            score += 20
            break
    return min(score, 100)


def list_providers() -> list[dict]:
    """Return available providers and their status."""
    return [
        {"id": "apify", "name": "Apify (AI Deep Job Search)", "needs_key": True},
        {"id": "linkedin_mcp", "name": "LinkedIn MCP", "needs_key": False},
        {"id": "both", "name": "Apify + LinkedIn MCP", "needs_key": True},
    ]
