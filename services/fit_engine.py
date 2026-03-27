"""
Phase 1 - Structured Fit Engine
Scores jobs against the candidate's truth inventory using:
  - role family match
  - seniority band match
  - experience evidence match
  - requirement evidence mapping (supported / partially_supported / unsupported / manual_review)
  - hard blockers
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from services.requirement_mapper import EvidenceContext, RequirementEvidence, map_requirements
from services.seniority_match import (
    detect_candidate_seniority as _detect_candidate_seniority,
    detect_job_seniority,
    score_seniority_match,
)

try:
    from services.truth_inventory_builder import ROLE_FAMILY_KEYWORDS, SKILL_EVIDENCE_PATTERNS, build_truth_inventory
except Exception:
    ROLE_FAMILY_KEYWORDS = {
        "ai_ml_engineer": ["machine learning", "ml engineer", "ai engineer"],
        "genai_engineer": ["generative ai", "llm", "rag"],
        "ai_agent_engineer": ["agent", "agentic", "autonomous agent"],
        "mlops_engineer": ["mlops", "ml platform", "model ops"],
        "data_scientist": ["data scientist", "data science"],
        "data_engineer": ["data engineer", "etl", "data pipeline"],
        "software_engineer": ["software engineer", "backend", "full stack"],
    }
    SKILL_EVIDENCE_PATTERNS = {
        "python": ["python"],
        "sql": ["sql"],
        "aws": ["aws"],
        "pytorch": ["pytorch"],
        "tensorflow": ["tensorflow"],
    }
    build_truth_inventory = None


ROLE_FAMILY_ALIASES = {
    "software_engineer": "software_engineer_ai",
}

ROLE_FAMILIES: dict[str, list[str]] = {
    "ai_ml_engineer": ROLE_FAMILY_KEYWORDS.get("ai_ml_engineer", []) + [
        "machine learning engineer",
        "ml engineer",
        "ai engineer",
        "applied scientist",
        "deep learning",
    ],
    "genai_engineer": ROLE_FAMILY_KEYWORDS.get("genai_engineer", []) + [
        "genai",
        "llm engineer",
        "rag engineer",
        "prompt engineer",
        "ai application engineer",
    ],
    "ai_agent_engineer": ROLE_FAMILY_KEYWORDS.get("ai_agent_engineer", []) + [
        "ai agent",
        "agentic",
        "autonomous agent",
    ],
    "mlops_engineer": ROLE_FAMILY_KEYWORDS.get("mlops_engineer", []) + [
        "mlops",
        "ml platform",
        "model ops",
        "feature store",
    ],
    "data_scientist": ROLE_FAMILY_KEYWORDS.get("data_scientist", []) + [
        "data scientist",
        "applied scientist",
        "research scientist",
    ],
    "data_engineer": ROLE_FAMILY_KEYWORDS.get("data_engineer", []) + [
        "data engineer",
        "etl",
        "data pipeline",
        "warehouse",
    ],
    "software_engineer_ai": ROLE_FAMILY_KEYWORDS.get("software_engineer", []) + [
        "software engineer",
        "backend engineer",
        "full stack",
        "platform engineer",
        "software developer",
    ],
}

CANDIDATE_ROLE_FAMILIES = [
    "ai_ml_engineer",
    "genai_engineer",
    "ai_agent_engineer",
    "mlops_engineer",
    "data_scientist",
]


@dataclass
class FitResult:
    role_family: str
    seniority_band: str
    role_match_score: int
    experience_match_score: int
    seniority_match_score: int
    overall_fit_score: int
    fit_decision: str  # apply | review_fit | skip
    fit_reasons: list[str]
    unsupported_requirements: list[str]
    hard_blockers: list[str]
    requirement_evidence_map: list[RequirementEvidence]
    supported_skills: list[str]
    missing_skills: list[str]


def _normalize_role_family(family: str) -> str:
    if not family:
        return ""
    fam = str(family).strip()
    return ROLE_FAMILY_ALIASES.get(fam, fam)


def _rank_role_families(text: str) -> list[str]:
    text_lower = (text or "").lower()
    scores: dict[str, int] = {}
    for family, keywords in ROLE_FAMILIES.items():
        score = sum(1 for kw in keywords if kw.lower() in text_lower)
        if score:
            scores[family] = score
    ranked = sorted(scores, key=lambda k: scores[k], reverse=True)
    return ranked


def detect_role_family(job_title: str, job_description: str = "") -> str:
    """Detect job role family from title + description."""
    text = f"{job_title} {job_description[:1200]}"
    ranked = _rank_role_families(text)
    return ranked[0] if ranked else "software_engineer_ai"


def infer_candidate_role_families(resume_text: str, profile: Optional[dict] = None) -> list[str]:
    families: list[str] = []
    if build_truth_inventory and resume_text:
        inv = build_truth_inventory(master_resume_text=resume_text, profile=profile or {})
        if inv.role_families:
            families = [_normalize_role_family(f) for f in inv.role_families if f]
    if not families and resume_text:
        families = _rank_role_families(resume_text)
    if not families:
        families = list(CANDIDATE_ROLE_FAMILIES)
    # De-dupe preserving order
    seen = set()
    out = []
    for f in families:
        if f in seen:
            continue
        seen.add(f)
        out.append(f)
    return out


def detect_seniority_band(job_title: str, job_description: str = "") -> str:
    return detect_job_seniority(job_title, job_description)


def detect_candidate_seniority(
    resume_text: str,
    profile: Optional[dict] = None,
    truth_inventory: Optional[dict] = None,
) -> str:
    return _detect_candidate_seniority(resume_text, profile=profile, truth_inventory=truth_inventory)


def extract_supported_skills(resume_text: str) -> set[str]:
    text_lower = (resume_text or "").lower()
    supported = set()
    for skill, patterns in SKILL_EVIDENCE_PATTERNS.items():
        for p in patterns:
            if p.lower() in text_lower:
                supported.add(skill)
                break
    return supported


def _score_role_match(job_family: str, primary_family: str, candidate_families: list[str]) -> int:
    jf = _normalize_role_family(job_family)
    pf = _normalize_role_family(primary_family)
    fams = [_normalize_role_family(f) for f in candidate_families]
    if jf == pf and jf:
        return 90
    if jf in fams:
        return 75
    # Adjacent: software_engineer_ai vs ai_ml_engineer/genai
    if jf == "software_engineer_ai" and any(f in fams for f in ["ai_ml_engineer", "genai_engineer"]):
        return 60
    return 40


def _experience_match_score(requirements: list[RequirementEvidence]) -> int:
    if not requirements:
        return 50
    supported = sum(1 for r in requirements if r.status == "supported")
    partial = sum(1 for r in requirements if r.status == "partially_supported")
    manual = sum(1 for r in requirements if r.status == "manual_review")
    unsupported = sum(1 for r in requirements if r.status == "unsupported")
    total = max(1, supported + partial + manual + unsupported)
    score = (supported + 0.6 * partial + 0.2 * manual) / total * 100
    if unsupported >= 3:
        score -= 8
    return int(max(5, min(98, round(score))))


def _detect_hard_blockers(
    job_description: str,
    resume_text: str,
    truth_inv: Optional[Any] = None,
    profile: Optional[dict] = None,
) -> list[str]:
    jd_lower = (job_description or "").lower()
    blockers: list[str] = []

    clearance_patterns = [
        "security clearance",
        "top secret",
        "ts/sci",
        "ts sci",
        "secret clearance",
    ]
    if any(p in jd_lower for p in clearance_patterns):
        blockers.append("Requires security clearance")

    if re.search(r"\bus citizens? only\b|\bcitizenship required\b|\bmust be a us citizen\b", jd_lower):
        blockers.append("Requires US citizenship")

    if "no sponsorship" in jd_lower or "without sponsorship" in jd_lower:
        requires_sponsorship = False
        if truth_inv is not None:
            requires_sponsorship = bool(getattr(truth_inv, "requires_sponsorship", False))
        if profile:
            vs = str(profile.get("visa_status", "")).lower()
            requires_sponsorship = requires_sponsorship or any(k in vs for k in ["opt", "h1b", "sponsor"])
        if requires_sponsorship:
            blockers.append("No visa sponsorship")

    # PhD required when resume lacks it
    if "phd required" in jd_lower and not re.search(r"\bphd\b", (resume_text or "").lower()):
        blockers.append("PhD required")

    years_match = re.search(r"(\d+)\+?\s+years?\s+(?:of\s+)?experience", jd_lower)
    if years_match:
        try:
            required_years = int(years_match.group(1))
        except Exception:
            required_years = 0
        if required_years >= 12:
            candidate_years = 0.0
            if truth_inv is not None:
                candidate_years = float(getattr(truth_inv, "total_years_experience", 0.0) or 0.0)
            if candidate_years and candidate_years + 5 < required_years:
                blockers.append(f"Requires {required_years}+ years experience")

    return blockers


def score_structured_fit(
    job_title: str,
    job_description: str,
    resume_text: str,
    profile: Optional[dict] = None,
    ats_score: int = 0,
) -> FitResult:
    profile = profile or {}

    truth_inv = None
    if build_truth_inventory and resume_text:
        truth_inv = build_truth_inventory(master_resume_text=resume_text, profile=profile)

    candidate_families: list[str] = []
    if truth_inv and getattr(truth_inv, "role_families", None):
        candidate_families = [_normalize_role_family(f) for f in truth_inv.role_families if f]
    if not candidate_families:
        candidate_families = infer_candidate_role_families(resume_text, profile)
    primary_family = candidate_families[0] if candidate_families else "ai_ml_engineer"
    if truth_inv and getattr(truth_inv, "primary_role_family", ""):
        primary_family = _normalize_role_family(getattr(truth_inv, "primary_role_family", "")) or primary_family

    job_family = detect_role_family(job_title, job_description)
    job_seniority = detect_job_seniority(job_title, job_description)

    candidate_seniority = detect_candidate_seniority(
        resume_text,
        profile=profile,
        truth_inventory={"seniority_band": getattr(truth_inv, "seniority_band", "") if truth_inv else ""},
    )

    role_match = _score_role_match(job_family, primary_family, candidate_families)
    seniority_match, seniority_gap = score_seniority_match(job_seniority, candidate_seniority)

    supported_skills = set(getattr(truth_inv, "skills_supported", []) or []) if truth_inv else extract_supported_skills(resume_text)
    partial_skills = set(getattr(truth_inv, "skills_partial", []) or []) if truth_inv else set()
    years_by_domain = getattr(truth_inv, "years_by_domain", {}) if truth_inv else {}
    total_years = float(getattr(truth_inv, "total_years_experience", 0.0) or 0.0) if truth_inv else 0.0
    education_text = getattr(truth_inv, "education_text", "") if truth_inv else ""

    ctx = EvidenceContext(
        resume_text=resume_text or "",
        supported_skills=supported_skills,
        partial_skills=partial_skills,
        years_by_domain=years_by_domain,
        total_years_experience=total_years,
        education_text=education_text,
    )

    req_evidence = map_requirements(job_description, ctx)
    exp_match = _experience_match_score(req_evidence)

    hard_blockers = _detect_hard_blockers(job_description, resume_text, truth_inv, profile)

    ats_contribution = int(min(max(ats_score, 0), 100) * 0.1) if ats_score else 0

    overall = int(
        role_match * 0.35
        + seniority_match * 0.25
        + exp_match * 0.30
        + ats_contribution
    )

    unsupported_reqs = [r.requirement for r in req_evidence if r.status == "unsupported"]

    fit_reasons: list[str] = []
    if job_family in candidate_families:
        fit_reasons.append(f"Role family '{job_family}' aligns with candidate background")
    else:
        fit_reasons.append(f"Role family '{job_family}' is outside primary focus areas")

    if seniority_gap == 0:
        fit_reasons.append(f"Seniority '{job_seniority}' matches candidate band '{candidate_seniority}'")
    elif seniority_gap == 1:
        fit_reasons.append(f"Seniority gap of 1 band (job: {job_seniority}, candidate: {candidate_seniority})")
    else:
        fit_reasons.append(f"Seniority gap of {seniority_gap} bands (job: {job_seniority}, candidate: {candidate_seniority})")

    if unsupported_reqs:
        fit_reasons.append(f"Unsupported requirements: {', '.join(unsupported_reqs[:3])}")

    decision = "review_fit"
    if hard_blockers:
        decision = "skip"
        fit_reasons.append(f"Hard blockers: {'; '.join(hard_blockers)}")
    elif role_match >= 70 and seniority_gap <= 1 and exp_match >= 65 and not unsupported_reqs:
        decision = "apply"
    elif overall >= 55 and role_match >= 50:
        decision = "review_fit"
    else:
        decision = "skip"

    return FitResult(
        role_family=job_family,
        seniority_band=job_seniority,
        role_match_score=role_match,
        experience_match_score=exp_match,
        seniority_match_score=seniority_match,
        overall_fit_score=overall,
        fit_decision=decision,
        fit_reasons=fit_reasons,
        unsupported_requirements=unsupported_reqs[:10],
        hard_blockers=hard_blockers,
        requirement_evidence_map=req_evidence,
        supported_skills=sorted(supported_skills),
        missing_skills=_missing_skills(supported_skills, partial_skills),
    )


def _missing_skills(supported: set[str], partial: set[str]) -> list[str]:
    all_skills = set(SKILL_EVIDENCE_PATTERNS.keys())
    missing = sorted(all_skills - supported - partial)
    return missing[:15]


def fit_result_to_dict(r: FitResult) -> dict:
    return {
        "role_family": r.role_family,
        "seniority_band": r.seniority_band,
        "role_match_score": r.role_match_score,
        "experience_match_score": r.experience_match_score,
        "seniority_match_score": r.seniority_match_score,
        "overall_fit_score": r.overall_fit_score,
        "fit_decision": r.fit_decision,
        "fit_reasons": r.fit_reasons,
        "unsupported_requirements": r.unsupported_requirements,
        "hard_blockers": r.hard_blockers,
        "requirement_evidence_map": [
            {
                "requirement": e.requirement,
                "status": e.status,
                "evidence": e.evidence,
                "confidence": e.confidence,
            }
            for e in r.requirement_evidence_map[:20]
        ],
        "supported_skills": r.supported_skills,
        "missing_skills": r.missing_skills,
    }
