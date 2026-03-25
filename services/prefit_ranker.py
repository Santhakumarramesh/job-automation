"""
Pre-fit ranking: single service for resume ↔ job overlap before deep fit/ATS.

Used by ``providers.registry.get_jobs`` and any caller that needs a consistent
``resume_match_score`` (or the same logic on arbitrary job dicts / rows).
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def prefit_keyword_bundle(resume_text: str) -> dict[str, list]:
    """Titles, locations, skills derived from master resume text (truth inventory–aware)."""
    from agents.master_resume_guard import extract_search_keywords

    return extract_search_keywords(resume_text or "")


def _job_texts(job: Any) -> tuple[str, str, str]:
    if hasattr(job, "title"):
        return (
            str(getattr(job, "title", "") or "").lower(),
            str(getattr(job, "description", "") or "").lower(),
            str(getattr(job, "location", "") or "").lower(),
        )
    if isinstance(job, Mapping):
        return (
            str(job.get("title") or "").lower(),
            str(job.get("description") or job.get("job_description") or "").lower(),
            str(job.get("location") or job.get("locationName") or "").lower(),
        )
    return "", "", ""


def prefit_score_job(job: Any, kw: dict[str, list]) -> int:
    """
    Simple overlap score 0–100: role phrase in title/description, skills in description,
    location hint in job location string.
    """
    title, desc, loc = _job_texts(job)
    score = 0
    for t in kw.get("job_titles") or []:
        tl = str(t).lower()
        if tl in title or tl in desc:
            score += 30
            break
    for s in kw.get("skills") or []:
        if str(s).lower() in desc:
            score += 8
    for loc_kw in kw.get("locations") or []:
        if str(loc_kw).lower() in loc:
            score += 20
            break
    return min(score, 100)


def rank_job_listings(
    jobs: Sequence[Any],
    *,
    resume_text: str | None = None,
    keyword_bundle: dict[str, list] | None = None,
) -> list[Any]:
    """Return jobs sorted by descending ``prefit_score_job``."""
    kw = keyword_bundle if keyword_bundle is not None else prefit_keyword_bundle(resume_text or "")
    scored = [(j, prefit_score_job(j, kw)) for j in jobs]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [j for j, _ in scored]


def add_prefit_scores_to_dataframe(df: Any, *, keyword_bundle: dict[str, list], column: str = "resume_match_score") -> Any:
    """Copy ``df``, set ``column`` from ``prefit_score_job`` per row, sort descending."""
    if df is None or len(df) == 0:
        return df
    out = df.copy()
    out[column] = [prefit_score_job(row, keyword_bundle) for _, row in out.iterrows()]
    return out.sort_values(column, ascending=False)
