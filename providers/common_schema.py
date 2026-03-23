"""
Normalized job schema for all providers.
Ensures Apify, LinkedIn MCP, and manual URLs produce identical structures.
"""

from dataclasses import dataclass, field
from typing import Any, Optional
import pandas as pd


@dataclass
class JobListing:
    """Normalized job listing used across providers."""
    title: str
    company: str
    location: str
    description: str
    url: str = ""
    work_type: str = ""  # remote, hybrid, on_site
    job_type: str = ""   # full_time, part_time, contract, internship
    posted_at: str = ""
    source: str = ""     # apify, linkedin_mcp, url
    salary: str = ""
    extra: dict = field(default_factory=dict)

    def to_row(self) -> dict:
        return {
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "description": self.description,
            "url": self.url,
            "work_type": self.work_type,
            "job_type": self.job_type,
            "posted_at": self.posted_at,
            "source": self.source,
            "salary": self.salary or "Not Available",
        }


def normalize_to_schema(raw: dict, source: str) -> JobListing:
    """Convert provider-specific dict to JobListing."""
    title = (
        raw.get("title")
        or raw.get("jobTitle")
        or raw.get("position")
        or raw.get("name")
        or "Unknown"
    )
    company = (
        raw.get("company")
        or raw.get("companyName")
        or raw.get("company_name")
        or ""
    )
    if isinstance(company, dict):
        company = company.get("name") or company.get("title") or ""
    location = (
        raw.get("location")
        or raw.get("locationName")
        or raw.get("place")
        or ""
    )
    if isinstance(location, dict):
        location = location.get("formatted", location.get("full", "")) or str(location)
    description = (
        raw.get("description")
        or raw.get("jobDescription")
        or raw.get("details")
        or raw.get("jobDetails")
        or ""
    )
    url = (
        raw.get("url")
        or raw.get("link")
        or raw.get("jobUrl")
        or raw.get("applyUrl")
        or ""
    )
    work_type = (
        raw.get("work_type")
        or raw.get("workType")
        or raw.get("remote")
        or ""
    )
    if isinstance(work_type, bool):
        work_type = "remote" if work_type else "on_site"
    job_type = raw.get("job_type") or raw.get("jobType") or raw.get("employmentType") or ""
    posted_at = raw.get("posted_at") or raw.get("postedAt") or raw.get("datePosted") or ""
    salary = raw.get("salary") or raw.get("salaryRange") or ""

    return JobListing(
        title=str(title),
        company=str(company),
        location=str(location),
        description=str(description),
        url=str(url),
        work_type=str(work_type),
        job_type=str(job_type),
        posted_at=str(posted_at),
        source=source,
        salary=str(salary) if salary else "",
        extra={k: v for k, v in raw.items() if k not in {
            "title", "company", "location", "description", "url",
            "work_type", "job_type", "posted_at", "salary",
            "jobTitle", "companyName", "jobDescription", "jobUrl",
            "workType", "postedAt", "datePosted", "salaryRange",
        }},
    )


def jobs_to_dataframe(jobs: list[JobListing]) -> pd.DataFrame:
    """Convert JobListing list to DataFrame for UI."""
    if not jobs:
        return pd.DataFrame()
    rows = [j.to_row() for j in jobs]
    return pd.DataFrame(rows)
