"""
Phase 3 — Discovery Ranker
Apply structured prefiltering to discovery results and return ranked buckets.
"""

from __future__ import annotations

from typing import Optional

from services.job_prefilter import JobPrefilterResult, prefilter_batch


def rank_discovery_results(
    jobs: list[dict],
    *,
    resume_text: str,
    profile: Optional[dict] = None,
    ats_scores: Optional[dict] = None,
) -> dict:
    """
    Return {high_confidence, review_fit, skip, ...} buckets with fit metadata.
    """
    return prefilter_batch(jobs, resume_text=resume_text, profile=profile, ats_scores=ats_scores)


def annotate_dataframe_with_prefilter(
    df,
    prefilter_result: dict,
    *,
    include_review: bool = True,
) -> any:
    """
    Add prefilter columns to dataframe and filter out skipped rows.
    """
    if df is None or len(df) == 0:
        return df

    by_url: dict[str, dict] = {}
    for bucket in ("high_confidence", "review_fit", "skip"):
        for row in prefilter_result.get(bucket, []) or []:
            url = row.get("job_url") or row.get("url") or ""
            if url:
                by_url[str(url)] = row

    out = df.copy()
    urls = out["url"] if "url" in out.columns else out.get("job_url", [])

    def _lookup(url):
        return by_url.get(str(url) or "", {})

    out["prefilter_classification"] = [
        _lookup(u).get("classification", JobPrefilterResult.SKIP) for u in urls
    ]
    out["prefilter_reason"] = [_lookup(u).get("reason", "") for u in urls]
    out["overall_fit_score"] = [_lookup(u).get("fit", {}).get("overall_fit_score", 0) for u in urls]
    out["seniority_match_score"] = [_lookup(u).get("fit", {}).get("seniority_match_score", 0) for u in urls]
    out["role_match_score"] = [_lookup(u).get("fit", {}).get("role_match_score", 0) for u in urls]

    if include_review:
        out = out[out["prefilter_classification"] != JobPrefilterResult.SKIP]
    else:
        out = out[out["prefilter_classification"] == JobPrefilterResult.HIGH_CONFIDENCE]

    out = out.sort_values(
        ["prefilter_classification", "overall_fit_score", "seniority_match_score", "role_match_score"],
        ascending=[True, False, False, False],
    )
    return out
