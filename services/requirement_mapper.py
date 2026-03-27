"""
Phase 1 - Requirement Mapper
Maps job description requirements to evidence statuses:
  supported | partially_supported | unsupported | manual_review
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

try:
    from services.truth_inventory_builder import SKILL_EVIDENCE_PATTERNS
except Exception:
    SKILL_EVIDENCE_PATTERNS = {
        "python": ["python"],
        "sql": ["sql"],
        "aws": ["aws", "amazon web services"],
        "pytorch": ["pytorch"],
        "tensorflow": ["tensorflow"],
        "nlp": ["nlp", "natural language"],
        "rag": ["rag", "retrieval augmented"],
        "docker": ["docker"],
        "kubernetes": ["kubernetes", "k8s"],
    }


SOFT_SKILL_HINTS = [
    "communication",
    "collaboration",
    "teamwork",
    "leadership",
    "stakeholder",
    "cross-functional",
    "problem solving",
    "critical thinking",
    "ownership",
    "mentoring",
]

REQUIREMENT_HEADERS = [
    "requirements",
    "qualifications",
    "minimum qualifications",
    "basic qualifications",
    "what you will need",
    "what you bring",
    "must have",
    "required",
]


@dataclass
class RequirementEvidence:
    requirement: str
    status: str  # supported | partially_supported | unsupported | manual_review
    evidence: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class EvidenceContext:
    resume_text: str
    supported_skills: set[str] = field(default_factory=set)
    partial_skills: set[str] = field(default_factory=set)
    years_by_domain: dict[str, float] = field(default_factory=dict)
    total_years_experience: float = 0.0
    education_text: str = ""


def _pattern_in_text(pattern: str, text: str) -> bool:
    if not pattern:
        return False
    p = pattern.lower().strip()
    if not p:
        return False
    if len(p) <= 3:
        return re.search(rf"\b{re.escape(p)}\b", text) is not None
    return p in text


def _skills_in_text(text: str) -> list[str]:
    matches = []
    for skill, patterns in SKILL_EVIDENCE_PATTERNS.items():
        for p in patterns:
            if _pattern_in_text(p, text):
                matches.append(skill)
                break
    return matches


def _clean_requirement(raw: str) -> str:
    s = raw.strip()
    s = re.sub(r"^[\-*\u2022\u2023\u25E6\u2043\u2219\d\.\)\s]+", "", s)
    s = s.strip(" \t:;-\u2022")
    s = re.sub(r"\s+", " ", s)
    return s[:180]


def _is_section_header(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if len(s) > 80:
        return False
    if s.endswith(":"):
        return True
    return s.isupper() and len(s) <= 60


def extract_major_requirements(job_description: str) -> list[str]:
    if not job_description:
        return []

    lines = [ln.strip() for ln in job_description.splitlines()]
    requirements: list[str] = []
    in_req_block = False
    blank_count = 0

    for line in lines:
        raw = line.strip()
        if not raw:
            blank_count += 1
            if blank_count >= 2:
                in_req_block = False
            continue
        blank_count = 0
        low = raw.lower()

        if any(h in low for h in REQUIREMENT_HEADERS):
            in_req_block = True
            continue

        if _is_section_header(raw):
            in_req_block = False

        if in_req_block:
            if raw.startswith(('-', '*', '\u2022')) or raw[:1].isdigit():
                cleaned = _clean_requirement(raw)
                if len(cleaned) >= 8:
                    requirements.append(cleaned)
                continue

        if any(k in low for k in ["must have", "required", "minimum", "experience with", "years of experience"]):
            cleaned = _clean_requirement(raw)
            if len(cleaned) >= 10:
                requirements.append(cleaned)

    # Pull explicit year/degree requirement fragments
    for m in re.finditer(r"\b\d+\+?\s+years?\b[^\n\.]{0,80}", job_description, re.I):
        req = _clean_requirement(m.group(0))
        if len(req) >= 8:
            requirements.append(req)

    for m in re.finditer(r"\b(bachelor|master|phd|doctorate)[^\n\.]{0,60}", job_description, re.I):
        req = _clean_requirement(m.group(0))
        if len(req) >= 8:
            requirements.append(req)

    # De-dupe preserving order
    seen = set()
    deduped: list[str] = []
    for req in requirements:
        key = req.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(req)
        if len(deduped) >= 15:
            break

    return deduped


def _infer_domain(text: str) -> Optional[str]:
    t = text.lower()
    domain_map = {
        "python": ["python"],
        "ml": ["machine learning", "ml", "deep learning", "pytorch", "tensorflow", "model"],
        "sql": ["sql", "postgres", "mysql", "snowflake", "bigquery"],
        "aws": ["aws", "amazon web services", "s3", "ec2", "sagemaker"],
        "nlp": ["nlp", "natural language"],
        "data": ["data engineer", "etl", "pipeline", "spark", "warehouse"],
    }
    for domain, hints in domain_map.items():
        if any(h in t for h in hints):
            return domain
    return None


def classify_requirement(req_text: str, ctx: EvidenceContext) -> RequirementEvidence:
    req_lower = req_text.lower()
    resume_lower = (ctx.resume_text or "").lower()

    # Degree requirements
    if re.search(r"\b(phd|required doctorate)\b", req_lower):
        if re.search(r"\bphd\b|doctorate", resume_lower):
            return RequirementEvidence(req_text, "supported", ["degree: phd"], 0.8)
        return RequirementEvidence(req_text, "unsupported", [], 0.1)

    if re.search(r"\b(bachelor|master|b\.s|m\.s|bs|ms)\b", req_lower):
        if re.search(r"\b(bachelor|master|b\.s|m\.s|bs|ms)\b", resume_lower):
            return RequirementEvidence(req_text, "supported", ["degree listed"], 0.8)
        return RequirementEvidence(req_text, "manual_review", ["degree unclear"], 0.3)

    # Years of experience requirements
    years_match = re.search(r"(\d+)\+?\s+years?\b", req_lower)
    if years_match:
        required_years = float(years_match.group(1))
        domain = _infer_domain(req_lower)
        candidate_years = ctx.total_years_experience
        if domain and domain in ctx.years_by_domain:
            candidate_years = ctx.years_by_domain.get(domain, candidate_years)

        if candidate_years >= required_years:
            return RequirementEvidence(req_text, "supported", [f"years_{domain or 'general'}={candidate_years:.1f}"], 0.85)
        if candidate_years >= max(0.0, required_years - 1):
            return RequirementEvidence(req_text, "partially_supported", [f"years_{domain or 'general'}={candidate_years:.1f}"], 0.6)
        return RequirementEvidence(req_text, "unsupported", [], 0.1)

    # Skill requirements
    matched_skills = _skills_in_text(req_lower)
    if matched_skills:
        supported = [s for s in matched_skills if s in ctx.supported_skills]
        partial = [s for s in matched_skills if s in ctx.partial_skills]
        if supported:
            return RequirementEvidence(req_text, "supported", supported[:3], 0.9)
        if partial:
            return RequirementEvidence(req_text, "partially_supported", partial[:3], 0.6)
        return RequirementEvidence(req_text, "unsupported", [], 0.15)

    # Soft skills or ambiguous requirements
    if any(k in req_lower for k in SOFT_SKILL_HINTS):
        return RequirementEvidence(req_text, "manual_review", ["soft skill"], 0.25)

    if "experience" in req_lower or "familiar" in req_lower:
        return RequirementEvidence(req_text, "manual_review", ["experience unclear"], 0.25)

    return RequirementEvidence(req_text, "manual_review", ["needs review"], 0.2)


def map_requirements(job_description: str, ctx: EvidenceContext) -> list[RequirementEvidence]:
    evidence_list: list[RequirementEvidence] = []
    reqs = extract_major_requirements(job_description)

    for req in reqs:
        evidence_list.append(classify_requirement(req, ctx))

    # Add skill mentions from JD if not already captured
    jd_lower = (job_description or "").lower()
    seen = {e.requirement.lower() for e in evidence_list}
    for skill, patterns in SKILL_EVIDENCE_PATTERNS.items():
        if any(_pattern_in_text(p, jd_lower) for p in patterns):
            label = f"Skill: {skill}"
            if label.lower() in seen:
                continue
            evidence_list.append(classify_requirement(label, ctx))
            seen.add(label.lower())

    return evidence_list
