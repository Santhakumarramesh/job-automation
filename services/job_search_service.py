"""
Job search service. get_jobs(provider, filters), uses registry.
"""

import pandas as pd
from typing import Optional

from services.enhanced_job_finder import EnhancedJobFinder
from providers.base_provider import SearchFilters


def get_jobs(
    resume_text: str,
    provider: str = "apify",
    apify_api_key: str = "",
    max_results: int = 50,
    filters: Optional[SearchFilters] = None,
) -> pd.DataFrame:
    """
    Find jobs via Apify, LinkedIn MCP, or both.
    Returns DataFrame with title, company, location, description, url, etc.
    """
    finder = EnhancedJobFinder(apify_api_key or "", provider=provider)
    return finder.find_jobs(resume_text, max_results=max_results, filters=filters)
