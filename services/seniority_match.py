"""
Phase 1 - Seniority Match
Detect job and candidate seniority bands and compute match scores.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple


SENIORITY_BANDS = {
    "intern": ["intern", "co-op", "coop", "student"],
    "entry": ["entry", "junior", "jr.", "jr ", "associate", "graduate", "new grad", "entry-level"],
    "mid": ["mid", "ii", "level 2", "level ii"],
    "senior": ["senior", "sr.", "sr ", "lead", "staff"],
    "staff_plus": ["staff", "principal", "distinguished", "architect", "director", "vp", "head of"],
}

BAND_ORDER = ["intern", "entry", "mid", "senior", "staff_plus"]


def detect_job_seniority(job_title: str, job_description: str = "") -> str:
    text = f"{job_title} {job_description}".lower()

    # Title keywords (highest priority)
    for band in ["staff_plus", "senior", "mid", "entry", "intern"]:
        if any(k in text for k in SENIORITY_BANDS[band]):
            return band

    # Years of experience heuristic
    years = _extract_required_years(text)
    if years is not None:
        if years >= 8:
            return "staff_plus"
        if years >= 5:
            return "senior"
        if years >= 3:
            return "mid"
        return "entry"

    return "mid"


def detect_candidate_seniority(
    resume_text: str,
    profile: Optional[dict] = None,
    truth_inventory: Optional[dict] = None,
) -> str:
    if truth_inventory and str(truth_inventory.get("seniority_band") or "").strip():
        return str(truth_inventory.get("seniority_band"))

    # Graduation date from profile
    if profile:
        grad_date = profile.get("graduation_date", "")
        if grad_date:
            m = re.search(r"(\d{4})", str(grad_date))
            if m:
                try:
                    from datetime import datetime

                    grad_year = int(m.group(1))
                    years = max(0, datetime.utcnow().year - grad_year)
                    if years <= 1:
                        return "entry"
                    if years <= 3:
                        return "entry"
                    if years <= 6:
                        return "mid"
                    if years <= 10:
                        return "senior"
                    return "staff_plus"
                except Exception:
                    pass

    # Resume text heuristic
    years_match = re.search(r"(\d+)\+?\s+years?\s+(?:of\s+)?experience", resume_text or "", re.I)
    if years_match:
        try:
            years = int(years_match.group(1))
            if years <= 1:
                return "entry"
            if years <= 3:
                return "mid"
            if years <= 6:
                return "senior"
            return "staff_plus"
        except Exception:
            pass

    text = (resume_text or "").lower()
    if any(k in text for k in ["staff engineer", "principal", "distinguished"]):
        return "staff_plus"
    if any(k in text for k in ["senior", "lead", "tech lead"]):
        return "senior"
    if any(k in text for k in ["junior", "associate", "intern", "entry"]):
        return "entry"

    return "mid"


def score_seniority_match(job_band: str, candidate_band: str) -> Tuple[int, int]:
    jb = job_band if job_band in BAND_ORDER else "mid"
    cb = candidate_band if candidate_band in BAND_ORDER else "mid"
    gap = abs(BAND_ORDER.index(jb) - BAND_ORDER.index(cb))
    score = max(0, 100 - gap * 25)
    return score, gap


def _extract_required_years(text: str) -> Optional[int]:
    m = re.search(r"(\d+)\+?\s+years?\s+(?:of\s+)?experience", text, re.I)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None
