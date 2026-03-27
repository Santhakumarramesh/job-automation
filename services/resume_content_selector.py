"""
Phase 2 - Resume Content Selector
Select relevant existing resume bullets and skills for ATS tailoring.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from services.keyword_coverage import analyze_keyword_coverage, build_truth_inventory_from_resume
from services.truth_inventory_builder import SKILL_EVIDENCE_PATTERNS


SECTION_HEADERS = {
    "summary": ["summary", "profile", "objective"],
    "experience": ["experience", "work history", "employment"],
    "projects": ["projects", "project"],
    "skills": ["skills", "technical skills", "core competencies"],
    "education": ["education", "academic"],
}


@dataclass
class SelectedContent:
    tailored_resume_text: str
    selected_experience_bullets: list[str] = field(default_factory=list)
    selected_project_bullets: list[str] = field(default_factory=list)
    skills_additions: list[str] = field(default_factory=list)
    skills_familiar_additions: list[str] = field(default_factory=list)
    coverage: Optional[dict] = None


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _split_sections(text: str) -> dict[str, list[str]]:
    sections = {k: [] for k in SECTION_HEADERS}
    current = None
    lines = (text or "").splitlines()
    for line in lines:
        raw = line.strip()
        if not raw:
            if current:
                sections[current].append("")
            continue
        low = raw.lower()
        header_hit = None
        for sec, headers in SECTION_HEADERS.items():
            if any(h in low and len(raw) <= 60 for h in headers):
                header_hit = sec
                break
        if header_hit:
            current = header_hit
            sections[current].append(raw)
            continue
        if current:
            sections[current].append(raw)
    return sections


def _extract_bullets(lines: list[str]) -> list[str]:
    bullets: list[str] = []
    for line in lines:
        raw = line.strip()
        if not raw:
            continue
        if raw.startswith(("-", "*", "\u2022")):
            bullets.append(raw.lstrip("-*\u2022 ").strip())
            continue
        if raw.startswith("\u2022"):
            bullets.append(raw.lstrip("\u2022 ").strip())
            continue
    return bullets


def _score_bullet(bullet: str, keywords: list[str], skill_terms: list[str]) -> int:
    text = _normalize(bullet)
    score = 0
    for kw in keywords:
        if kw and kw in text:
            score += 2
    for st in skill_terms:
        if not st:
            continue
        patterns = SKILL_EVIDENCE_PATTERNS.get(st, [])
        if any(p.lower() in text for p in patterns):
            score += 3
    return score


def _select_top(bullets: list[str], keywords: list[str], skill_terms: list[str], limit: int) -> list[str]:
    scored = [(b, _score_bullet(b, keywords, skill_terms)) for b in bullets]
    scored.sort(key=lambda x: x[1], reverse=True)
    top = [b for b, s in scored if s > 0]
    if not top:
        top = [b for b, _ in scored]
    return top[:limit]


def _build_skills_line(
    supported: list[str],
    partial: list[str],
    additions: list[str],
    familiar_additions: Optional[list[str]] = None,
) -> str:
    skills = []
    for s in supported:
        if s and s not in skills:
            skills.append(s)
    for s in additions:
        if s and s not in skills:
            skills.append(s)
    skills_line = ""
    if skills:
        skills_line = "Relevant Skills: " + ", ".join(skills[:20])
    combined_partial = list(partial)
    if familiar_additions:
        for p in familiar_additions:
            if p and p not in combined_partial:
                combined_partial.append(p)
    if combined_partial:
        part = ", ".join([p for p in combined_partial if p not in skills][:10])
        if part:
            skills_line = (skills_line + "\n" if skills_line else "") + "Familiar: " + part
    return skills_line


def _filter_additions(
    additions: list[str],
    coverage: Optional[dict],
    supported: list[str],
    partial: list[str],
) -> tuple[list[str], list[str]]:
    supported_lower = {s.lower() for s in supported}
    partial_lower = {s.lower() for s in partial}
    support_map = {}
    if coverage:
        support_map = {str(k).lower(): str(v) for k, v in (coverage.get("support_level_map") or {}).items()}

    supported_out: list[str] = []
    familiar_out: list[str] = []
    for raw in additions:
        if not raw:
            continue
        low = raw.lower().strip()
        if not low:
            continue
        if low in supported_lower:
            if raw not in supported_out:
                supported_out.append(raw)
            continue
        if low in partial_lower:
            if raw not in familiar_out:
                familiar_out.append(raw)
            continue
        level = support_map.get(low)
        if level == "supported":
            if raw not in supported_out:
                supported_out.append(raw)
        elif level == "partially_supported":
            if raw not in familiar_out:
                familiar_out.append(raw)
    return supported_out, familiar_out


def select_relevant_content(
    master_resume_text: str,
    job_description: str,
    profile: Optional[dict] = None,
    additional_keywords: Optional[list[str]] = None,
    max_experience_bullets: int = 6,
    max_project_bullets: int = 4,
) -> SelectedContent:
    base_text = master_resume_text or ""
    truth_inv = build_truth_inventory_from_resume(base_text, profile=profile)
    coverage = analyze_keyword_coverage(job_description, base_text, truth_inv)

    sections = _split_sections(base_text)
    exp_bullets = _extract_bullets(sections.get("experience") or [])
    proj_bullets = _extract_bullets(sections.get("projects") or [])

    keywords = coverage.job_keywords
    skill_terms = coverage.job_skill_terms
    weighted_keywords = list(dict.fromkeys(keywords + coverage.supported_keywords + coverage.partially_supported_keywords))

    selected_exp = _select_top(exp_bullets, weighted_keywords, skill_terms, max_experience_bullets)
    selected_proj = _select_top(proj_bullets, weighted_keywords, skill_terms, max_project_bullets)

    additions = list(coverage.truthful_expansion_keywords)
    if additional_keywords:
        for k in additional_keywords:
            if k and k not in additions:
                additions.append(k)

    supported = truth_inv.get("skills_supported", []) if truth_inv else []
    partial = truth_inv.get("skills_partial", []) if truth_inv else []
    safe_additions, familiar_additions = _filter_additions(additions, coverage.__dict__ if coverage else None, supported, partial)
    skills_line = _build_skills_line(supported, partial, safe_additions, familiar_additions=familiar_additions)

    highlights: list[str] = []
    if selected_exp:
        highlights.append("Relevant Experience Highlights:")
        highlights.extend([f"- {b}" for b in selected_exp])
    if selected_proj:
        highlights.append("Relevant Project Highlights:")
        highlights.extend([f"- {b}" for b in selected_proj])

    tailored = base_text.strip()
    if skills_line:
        tailored = (tailored + "\n\n" + skills_line).strip()
    if highlights:
        tailored = (tailored + "\n\n" + "\n".join(highlights)).strip()

    return SelectedContent(
        tailored_resume_text=tailored,
        selected_experience_bullets=selected_exp,
        selected_project_bullets=selected_proj,
        skills_additions=safe_additions,
        skills_familiar_additions=familiar_additions,
        coverage={
            "covered_keywords": coverage.covered_keywords,
            "supported_keywords": coverage.supported_keywords,
            "partially_supported_keywords": coverage.partially_supported_keywords,
            "truthful_missing_keywords": coverage.truthful_missing_keywords,
            "unsupported_keywords": coverage.unsupported_keywords,
            "support_level_map": coverage.support_level_map,
        },
    )
