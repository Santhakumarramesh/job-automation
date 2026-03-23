"""
Job finder - delegates to provider registry.
Supports Apify, LinkedIn MCP, or both.
"""

import os
import pandas as pd
from providers.registry import get_jobs, list_providers
from providers.common_schema import JobListing


class EnhancedJobFinder:
    """Unified job finder using Apify and/or LinkedIn MCP providers."""

    def __init__(self, apify_api_key: str, provider: str = "apify"):
        self.apify_api_key = apify_api_key or ""
        self.provider = provider if provider in ("apify", "linkedin_mcp", "both") else "apify"

    def analyze_resume_for_keywords(self, resume_text: str):
        """Legacy: kept for compatibility. Use get_jobs for new code."""
        from providers.registry import _analyze_resume_keywords
        kw = _analyze_resume_keywords(resume_text)
        return {
            "skills": kw["skills"],
            "job_titles": kw["job_titles"],
            "preferred_locations": kw["locations"],
        }

    def find_jobs_with_apify(self, resume_text: str, max_results: int = 50) -> pd.DataFrame:
        """Find jobs. Uses Apify, LinkedIn MCP, or both based on self.provider."""
        df, _ = get_jobs(
            provider=self.provider,
            resume_text=resume_text,
            apify_api_key=self.apify_api_key,
            max_results=max_results,
        )
        return df

    def save_results_to_excel(self, jobs_df: pd.DataFrame, filename: str = "job_search_results.xlsx") -> str | None:
        """Save job results to Excel."""
        if jobs_df.empty:
            print("No jobs to save")
            return None

        main_cols = ["title", "company", "location", "description", "url", "resume_match_score", "search_date"]
        cols = [c for c in main_cols if c in jobs_df.columns]
        main_df = jobs_df[cols] if cols else jobs_df

        with pd.ExcelWriter(filename, engine="openpyxl") as writer:
            main_df.to_excel(writer, sheet_name="Job_Results", index=False)
            summary = pd.DataFrame({
                "Metric": ["Total Jobs Found", "Average Match Score", "Top Company", "Top Location"],
                "Value": [
                    len(jobs_df),
                    jobs_df["resume_match_score"].mean() if "resume_match_score" in jobs_df.columns else 0,
                    jobs_df["company"].mode().iloc[0] if "company" in jobs_df.columns and not jobs_df["company"].mode().empty else "N/A",
                    jobs_df["location"].mode().iloc[0] if "location" in jobs_df.columns and not jobs_df["location"].mode().empty else "N/A",
                ],
            })
            summary.to_excel(writer, sheet_name="Summary", index=False)
            if "resume_match_score" in jobs_df.columns:
                top = jobs_df[jobs_df["resume_match_score"] > 70]
                if not top.empty:
                    top[main_cols].to_excel(writer, sheet_name="Top_Matches", index=False)

        print(f"Results saved to {filename}")
        return filename


if __name__ == "__main__":
    apify_key = os.getenv("APIFY_API_KEY") or os.getenv("APIFY_API_TOKEN")
    if not apify_key:
        print("Set APIFY_API_KEY or APIFY_API_TOKEN")
    else:
        finder = EnhancedJobFinder(apify_key, provider="apify")
        sample = "AI/ML Engineer with Python, TensorFlow, AWS. USA, Remote."
        df = finder.find_jobs_with_apify(sample, max_results=20)
        if not df.empty:
            finder.save_results_to_excel(df)
            print(df[["title", "company", "location", "resume_match_score"]].head())
