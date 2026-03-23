"""
Master Resume Guard - Truth-safe inventory and JD fit gate.
Parses master resume to build allowed skills/claims inventory.
Rejects unsupported keyword stuffing and decides whether a JD is a truthful match.
"""

import re
import json
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage


def parse_master_resume(master_resume_text: str) -> dict:
    """
    Parse master resume to build allowed inventory:
    - skills, tools, technologies
    - projects, education, experience claims
    """
    if not master_resume_text or len(master_resume_text.strip()) < 100:
        return {
            "skills": set(),
            "tools": set(),
            "projects": set(),
            "education": set(),
            "companies": set(),
            "raw_text_lower": "",
        }

    text = master_resume_text.strip()
    text_lower = text.lower()

    # Common tech/skills patterns
    tech_phrases = [
        "python", "sql", "aws", "azure", "gcp", "tensorflow", "pytorch", "scikit-learn",
        "machine learning", "deep learning", "nlp", "data pipeline", "etl", "docker",
        "kubernetes", "spark", "pyspark", "tableau", "power bi", "excel", "git", "ci/cd",
        "rest api", "javascript", "react", "java", "scala", "r programming",
        "pandas", "numpy", "keras", "cnn", "lstm", "xgboost", "random forest",
        "agile", "scrum", "jira", "confluence", "snowflake", "databricks", "redshift",
        "langchain", "rag", "llm", "openai", "hugging face", "transformers",
    ]

    skills = set()
    for p in tech_phrases:
        if p in text_lower:
            skills.add(p)

    # Extract from Skills section (between ## Skills / Technical Skills and next ##)
    skills_section = _extract_section(text, ["skills", "technical skills", "core competencies"])
    if skills_section:
        words = set(re.findall(r'\b[a-z0-9+#\.\-]{2,30}\b', skills_section.lower()))
        stop = {"the", "and", "or", "for", "with", "etc", "including"}
        for w in words:
            if w not in stop and len(w) >= 2:
                skills.add(w)

    # Extract project names (### Project Title or ## Projects)
    projects = set()
    for m in re.finditer(r'(?:^##\s+Projects?|^###\s+)([^\n#]+)', text, re.M | re.I):
        name = m.group(1).strip()
        if len(name) > 3 and len(name) < 80:
            projects.add(name)

    # Extract education
    education = set()
    edu_section = _extract_section(text, ["education", "academic"])
    if edu_section:
        for m in re.finditer(r'\b(bs|ms|phd|bachelor|master|mba|b\.?s\.?|m\.?s\.?)\b', edu_section, re.I):
            education.add(m.group(1).lower())
        for m in re.findall(r'\b[a-z]+(?:\s+[a-z]+)?\s+(?:university|college|institute)\b', edu_section, re.I):
            education.add(m.strip().lower())

    # Extract company names (experience section)
    companies = set()
    exp_section = _extract_section(text, ["experience", "work experience", "professional experience", "employment"])
    if exp_section:
        for m in re.finditer(r'\*\*([^*]+)\*\*', exp_section):
            company = m.group(1).strip()
            if len(company) > 2 and len(company) < 60 and not company.isdigit():
                companies.add(company)

    return {
        "skills": skills,
        "tools": skills,  # same set for now
        "projects": projects,
        "education": education,
        "companies": companies,
        "raw_text_lower": text_lower,
    }


def _extract_section(text: str, section_names: list[str]) -> str:
    """Extract content between ## SectionName and next ##."""
    text_upper = text.upper()
    start = -1
    for name in section_names:
        pat = rf'^#+\s*{re.escape(name)}\s*$'
        m = re.search(pat, text, re.M | re.I)
        if m:
            start = m.end()
            break
    if start < 0:
        return ""
    next_sec = re.search(r'\n#+\s+', text[start:])
    end = start + next_sec.start() if next_sec else len(text)
    return text[start:end]


def get_truthful_missing_keywords(
    master_inventory: dict,
    jd_missing_keywords: list[str],
) -> list[str]:
    """
    Filter JD missing keywords to only those that CAN be added from master resume.
    A keyword is truthful if it appears in master (skill/tool) or is a close synonym
    of something in master (e.g., "ML" -> "machine learning").
    """
    allowed = master_inventory.get("skills", set()) | master_inventory.get("tools", set())
    allowed_lower = {s.lower() for s in allowed}
    truthful = []
    for kw in jd_missing_keywords:
        k = kw.lower().strip()
        if not k or len(k) < 2:
            continue
        if k in allowed_lower:
            truthful.append(kw)
            continue
        # Check substring (e.g., "machine learning" covers "ml")
        for a in allowed_lower:
            if k in a or a in k:
                truthful.append(kw)
                break
    return truthful


def get_unsupported_requirements(
    jd_keywords: list[str],
    master_inventory: dict,
) -> list[str]:
    """
    Return JD requirements that are NOT supported by master resume.
    These would require fake additions to hit 100 ATS.
    """
    allowed = master_inventory.get("skills", set()) | master_inventory.get("tools", set())
    allowed_lower = {s.lower() for s in allowed}
    unsupported = []
    for kw in jd_keywords:
        k = kw.lower().strip()
        if not k or len(k) < 3:
            continue
        found = k in allowed_lower
        if not found:
            for a in allowed_lower:
                if k in a or a in k:
                    found = True
                    break
        if not found:
            unsupported.append(kw)
    return unsupported


def compute_job_fit_score(
    jd_text: str,
    master_inventory: dict,
    ats_score: int = 0,
) -> dict:
    """
    Compute job-fit score and gate decision.
    Returns: { score 0-100, apply, review, reject, reasons }
    """
    reasons = []
    score = 100

    # Sponsorship / citizenship
    if re.search(r'u\.?s\.?\s*citizen|citizenship\s*required|clearance\s*required', jd_text, re.I):
        score = 0
        reasons.append("Requires US Citizenship or clearance")
        return {"score": 0, "apply": False, "review": False, "reject": True, "reasons": reasons}

    # Years of experience
    yoe_match = re.search(r'(\d+)\+?\s*years?\s*(?:of\s*)?experience', jd_text, re.I)
    if yoe_match:
        required_yoe = int(yoe_match.group(1))
        if required_yoe >= 8:
            score -= 25
            reasons.append(f"Role asks for {required_yoe}+ years experience")
        elif required_yoe >= 5:
            score -= 10
            reasons.append(f"Role asks for {required_yoe}+ years experience")

    # Extract critical JD skills
    jd_keywords = _extract_jd_keywords(jd_text)
    unsupported = get_unsupported_requirements(jd_keywords[:20], master_inventory)
    if len(unsupported) >= 5:
        score -= 30
        reasons.append(f"5+ core JD skills not in master resume: {', '.join(unsupported[:5])}")
    elif unsupported:
        score -= 10
        reasons.append(f"Some JD skills not supported: {', '.join(unsupported[:3])}")

    # ATS score gate
    if ats_score < 100:
        score -= 15
        reasons.append(f"Internal ATS score {ats_score} < 100")

    score = max(0, min(100, score))

    apply = score >= 90 and ats_score >= 100 and len(unsupported) == 0
    reject = score < 50 or (len(unsupported) >= 5)
    review = not apply and not reject

    return {
        "score": score,
        "apply": apply,
        "review": review,
        "reject": reject,
        "reasons": reasons,
        "unsupported_requirements": unsupported,
    }


def _extract_jd_keywords(jd_text: str) -> list[str]:
    """Extract key skills/technologies from JD."""
    tech_phrases = [
        "python", "sql", "aws", "azure", "gcp", "tensorflow", "pytorch", "machine learning",
        "deep learning", "nlp", "docker", "kubernetes", "spark", "scala", "java",
        "langchain", "rag", "llm", "snowflake", "databricks", "redshift",
    ]
    found = [p for p in tech_phrases if p in jd_text.lower()]
    words = re.findall(r'\b[a-z0-9+#\.\-]{3,20}\b', jd_text.lower())
    stop = {"the", "and", "for", "with", "this", "that", "have", "from"}
    for w in words:
        if w not in stop and w not in found:
            found.append(w)
    return list(dict.fromkeys(found))[:25]


def is_truthful_match(master_resume_text: str, jd_text: str) -> tuple[bool, str]:
    """
    Quick check: is this JD a truthful fit for the master resume?
    Returns (is_match, reason).
    """
    inv = parse_master_resume(master_resume_text)
    jd_kw = _extract_jd_keywords(jd_text)
    unsupported = get_unsupported_requirements(jd_kw[:15], inv)
    fit = compute_job_fit_score(jd_text, inv, ats_score=100)

    if fit["reject"]:
        return False, "; ".join(fit["reasons"][:3])
    if fit["apply"]:
        return True, "Full fit"
    return True, "Review recommended: " + "; ".join(fit["reasons"][:2])
