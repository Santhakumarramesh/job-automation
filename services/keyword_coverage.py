"""
Phase 2 - Keyword Coverage
Analyze JD keywords against resume and truth inventory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

try:
    from services.truth_inventory_builder import SKILL_EVIDENCE_PATTERNS, build_truth_inventory
except Exception:
    SKILL_EVIDENCE_PATTERNS = {
        "python": ["python"],
        "sql": ["sql"],
        "aws": ["aws", "amazon web services"],
        "pytorch": ["pytorch"],
        "tensorflow": ["tensorflow"],
        "nlp": ["nlp", "natural language"],
        "rag": ["rag", "retrieval augmented"],
        "llm": ["llm", "large language model", "gpt", "chatgpt"],
        "genai": ["generative ai", "genai", "gen ai"],
        "mlops": ["mlops", "ml ops", "machine learning operations"],
        "deep_learning": ["deep learning", "neural network", "cnn", "lstm"],
        "ci_cd": ["ci/cd", "continuous integration", "continuous deployment"],
    }
    build_truth_inventory = None


STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "are", "you", "our", "can",
    "will", "from", "have", "has", "not", "but", "they", "your", "its", "all",
    "experience", "required", "skills", "role", "team", "work", "build", "using",
    "ability", "preferred", "plus", "years", "year", "strong", "knowledge",
    "including", "related", "field", "degree", "minimum", "must",
}


@dataclass
class KeywordCoverage:
    job_keywords: list[str] = field(default_factory=list)
    job_skill_terms: list[str] = field(default_factory=list)
    covered_keywords: list[str] = field(default_factory=list)
    supported_keywords: list[str] = field(default_factory=list)
    partially_supported_keywords: list[str] = field(default_factory=list)
    truthful_missing_keywords: list[str] = field(default_factory=list)
    unsupported_keywords: list[str] = field(default_factory=list)
    truthful_expansion_keywords: list[str] = field(default_factory=list)
    evidence_map: dict[str, list[str]] = field(default_factory=dict)
    support_level_map: dict[str, str] = field(default_factory=dict)


def _pattern_in_text(pattern: str, text: str) -> bool:
    if not pattern:
        return False
    p = pattern.lower().strip()
    if not p:
        return False
    if len(p) <= 3:
        return re.search(rf"\b{re.escape(p)}\b", text) is not None
    return p in text


def _extract_tokens(text: str) -> list[str]:
    tokens = re.findall(r"\b[a-z][a-z0-9\+#\.]{2,}\b", text.lower())
    return [t for t in tokens if t not in STOPWORDS]


def extract_job_keywords(job_description: str) -> list[str]:
    if not job_description:
        return []
    jd_lower = job_description.lower()
    tokens = _extract_tokens(job_description)

    # Add explicit JD skill phrases
    for skill, patterns in SKILL_EVIDENCE_PATTERNS.items():
        for p in patterns:
            if p.lower() in jd_lower:
                tokens.append(p.lower())
                break

    # De-dupe preserve order
    seen = set()
    out = []
    for t in tokens:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out[:40]


def _job_skill_terms(job_description: str) -> dict[str, str]:
    """Return canonical skill -> jd phrase hit."""
    jd_lower = (job_description or "").lower()
    hits: dict[str, str] = {}
    for skill, patterns in SKILL_EVIDENCE_PATTERNS.items():
        for p in patterns:
            pl = p.lower()
            if pl in jd_lower:
                hits[skill] = pl
                break
    return hits


def _supported_skill_sets(resume_text: str, truth_inventory: Optional[dict]) -> tuple[set[str], set[str]]:
    supported: set[str] = set()
    partial: set[str] = set()
    if truth_inventory:
        supported = set(truth_inventory.get("skills_supported") or [])
        partial = set(truth_inventory.get("skills_partial") or [])
    if not supported and resume_text:
        resume_lower = resume_text.lower()
        for skill, patterns in SKILL_EVIDENCE_PATTERNS.items():
            if any(p.lower() in resume_lower for p in patterns):
                supported.add(skill)
    return supported, partial


def analyze_keyword_coverage(
    job_description: str,
    resume_text: str,
    truth_inventory: Optional[dict] = None,
) -> KeywordCoverage:
    resume_lower = (resume_text or "").lower()

    job_keywords = extract_job_keywords(job_description)
    skill_hits = _job_skill_terms(job_description)

    supported_skills, partial_skills = _supported_skill_sets(resume_text, truth_inventory)

    covered = [kw for kw in job_keywords if _pattern_in_text(kw, resume_lower)]

    truthful_missing: list[str] = []
    unsupported: list[str] = []
    expansion: list[str] = []
    evidence_map: dict[str, list[str]] = {}
    supported_phrases: list[str] = []
    partial_phrases: list[str] = []
    support_level_map: dict[str, str] = {}

    for skill, jd_phrase in skill_hits.items():
        phrase_key = jd_phrase.lower()
        if skill in supported_skills or skill in partial_skills:
            evidence_map[jd_phrase] = [skill]
            if skill in supported_skills:
                support_level_map[phrase_key] = "supported"
                supported_phrases.append(jd_phrase)
                if jd_phrase not in resume_lower:
                    expansion.append(jd_phrase)
                    truthful_missing.append(skill)
            else:
                support_level_map[phrase_key] = "partially_supported"
                partial_phrases.append(jd_phrase)
        else:
            unsupported.append(skill)
            evidence_map[jd_phrase] = []
            support_level_map[phrase_key] = "unsupported"

    def _dedupe(seq: list[str]) -> list[str]:
        seen = set()
        out: list[str] = []
        for s in seq:
            if s in seen:
                continue
            seen.add(s)
            out.append(s)
        return out

    return KeywordCoverage(
        job_keywords=job_keywords,
        job_skill_terms=list(skill_hits.keys()),
        covered_keywords=_dedupe(covered)[:30],
        supported_keywords=_dedupe(supported_phrases)[:20],
        partially_supported_keywords=_dedupe(partial_phrases)[:20],
        truthful_missing_keywords=_dedupe(truthful_missing)[:20],
        unsupported_keywords=_dedupe(unsupported)[:20],
        truthful_expansion_keywords=_dedupe(expansion)[:15],
        evidence_map=evidence_map,
        support_level_map=support_level_map,
    )


def build_truth_inventory_from_resume(resume_text: str, profile: Optional[dict] = None) -> Optional[dict]:
    if not build_truth_inventory:
        return None
    inv = build_truth_inventory(master_resume_text=resume_text or "", profile=profile or {})
    return {
        "skills_supported": inv.skills_supported,
        "skills_partial": inv.skills_partial,
        "years_by_domain": inv.years_by_domain,
        "total_years_experience": inv.total_years_experience,
        "summary_text": inv.summary_text,
        "work_experience_text": inv.work_experience_text,
        "projects_text": inv.projects_text,
        "education_text": inv.education_text,
        "skills_section_text": inv.skills_section_text,
    }
