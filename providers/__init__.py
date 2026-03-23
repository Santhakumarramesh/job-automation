"""
Job providers: Apify, LinkedIn MCP, and shared schema.
Unified flow: providers -> normalized jobs -> ATS -> tailored docs -> tracker
"""

from providers.common_schema import JobListing, normalize_to_schema
from providers.registry import get_jobs, list_providers

__all__ = ["JobListing", "normalize_to_schema", "get_jobs", "list_providers"]
