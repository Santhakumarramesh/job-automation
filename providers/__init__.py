"""
Job providers: Apify, LinkedIn MCP, and shared schema.
Unified flow: providers -> normalized jobs -> ATS -> tailored docs -> tracker
"""

from providers.common_schema import JobListing, normalize_to_schema, jobs_to_dataframe
from providers.base_provider import JobProvider, SearchFilters
from providers.registry import get_jobs, get_provider, list_providers

__all__ = [
    "JobListing",
    "normalize_to_schema",
    "jobs_to_dataframe",
    "JobProvider",
    "SearchFilters",
    "get_jobs",
    "get_provider",
    "list_providers",
]
