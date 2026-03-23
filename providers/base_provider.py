"""
Abstract base for job providers. Apify and LinkedIn MCP implement this interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from providers.common_schema import JobListing


@dataclass
class SearchFilters:
    """Filters for job search. Provider-specific; pass through what each supports."""
    date_posted: str = ""      # 24h, 1w, 1m (LinkedIn)
    job_type: str = ""         # full_time, part_time, contract, internship
    experience_level: str = "" # entry, mid, senior
    work_remote: str = ""      # remote, hybrid, on_site
    easy_apply: bool = False
    sort_order: str = ""      # most_recent, most_relevant (LinkedIn)


class JobProvider(ABC):
    """Abstract job provider. Implement search() and get_job_details()."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Provider identifier: apify, linkedin_mcp, etc."""
        pass

    @abstractmethod
    def search(
        self,
        keywords: list[str],
        location: str,
        filters: SearchFilters,
        max_results: int,
    ) -> list[JobListing]:
        """
        Search for jobs. Returns normalized JobListing list.
        """
        pass

    @abstractmethod
    def get_job_details(self, job_id: str) -> Optional[JobListing]:
        """
        Fetch full job details by provider job_id.
        Returns None if not found or provider doesn't support it.
        """
        pass
