"""
Master Resume Guard - Truth-safe inventory and JD fit gate.
Parses master resume to build allowed skills/claims inventory.
Rejects unsupported keyword stuffing and decides whether a JD is a truthful match.
"""

import re
import json
from dataclasses import dataclass, field
from typing import Optional, Union

try:
    from providers.common_schema import JobListing
except ImportError:
    JobListing = None  # type: ignore


@dataclass
class CandidateProfile:
    """Full inventory from master resume. Central gatekeeper for job fit."""
    skills: set = field(default_factory=set)
    tools: set = field(default_factory=set)
    projects: set = field(default_factory=set)
    education: set = field(default_factory=set)
    companies: set = field(default_factory=set)
    locations: list = field(default_factory=list)
    visa_status: str = ""
    work_authorization: str = ""
    github_url: str = ""
    linkedin_url: str = ""
    portfolio_url: str = ""
    preferred_roles: list = field(default_factory=list)
    years_experience: dict = field(default_factory=dict)
    raw_text_lower: str = ""

    def to_dict(self) -> dict:
        """Legacy: dict format for get_truthful_missing_keywords etc."""
        return {
            "skills": self.skills,
            "tools": self.tools,
            "projects": self.projects,
            "education": self.education,
            "companies": self.companies,
            "raw_text_lower": self.raw_text_lower,
        }

    def allowed_skills_list(self) -> list:
        """Skills + tools as list for tailor_resume allowed_skills."""
        return list(self.skills | self.tools)


@dataclass
class FitResult:
    """Result of job fit check. Decision: apply, review, or reject."""
    decision: str  # "apply" | "review" | "reject"
    score: int
    reasons: list
    unsupported_requirements: list
    apply: bool
    review: bool
    reject: bool


def parse_master_resume(master_resume_text: str) -> CandidateProfile:
    """
    Parse master resume to build allowed inventory:
    - skills, tools, technologies
    - projects, education, experience claims
    """
    if not master_resume_text or len(master_resume_text.strip()) < 100:
        return CandidateProfile()

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

    # Locations: prefer Remote, USA from resume or common patterns
    locations = ["USA", "Remote"]
    if re.search(r'\bremote\b', text_lower):
        locations.insert(0, "Remote")
    for m in re.finditer(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*,?\s*(?:CA|NY|TX|WA|USA))\b', text):
        loc = m.group(1).strip()
        if loc and loc not in locations:
            locations.append(loc)

    # Visa / work auth: infer from common phrases
    visa_status = ""
    work_authorization = ""
    if re.search(r'f1\s*opt|opt\s*student|authorized\s*to\s*work', text_lower):
        visa_status = "F1 OPT"
        work_authorization = "Immediate availability, no sponsorship required"
    elif re.search(r'green\s*card|permanent\s*resident|us\s*citizen', text_lower):
        visa_status = "Green Card / Citizen"
        work_authorization = "Authorized to work in US"

    # URLs
    github_url = ""
    linkedin_url = ""
    portfolio_url = ""
    for m in re.finditer(r'https?://(?:www\.)?(github\.com/[^\s\)]+)', text, re.I):
        github_url = m.group(0).strip()
        break
    for m in re.finditer(r'https?://(?:www\.)?(linkedin\.com/[^\s\)]+)', text, re.I):
        linkedin_url = m.group(0).strip()
        break

    return CandidateProfile(
        skills=skills,
        tools=skills,
        projects=projects,
        education=education,
        companies=companies,
        locations=locations[:10],
        visa_status=visa_status,
        work_authorization=work_authorization,
        github_url=github_url,
        linkedin_url=linkedin_url,
        portfolio_url=portfolio_url,
        preferred_roles=["AI/ML Engineer", "Machine Learning Engineer"] if "ml" in text_lower or "ai" in text_lower else [],
        raw_text_lower=text_lower,
    )


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


def _as_inventory(master_inventory: Union[CandidateProfile, dict]) -> dict:
    """Normalize to dict for skills/tools access."""
    if isinstance(master_inventory, CandidateProfile):
        return master_inventory.to_dict()
    return master_inventory


def get_truthful_missing_keywords(
    master_inventory: Union[CandidateProfile, dict],
    jd_missing_keywords: list[str],
) -> list[str]:
    """
    Filter JD missing keywords to only those that CAN be added from master resume.
    A keyword is truthful if it appears in master (skill/tool) or is a close synonym
    of something in master (e.g., "ML" -> "machine learning").
    """
    inv = _as_inventory(master_inventory)
    allowed = inv.get("skills", set()) | inv.get("tools", set())
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
    master_inventory: Union[CandidateProfile, dict],
) -> list[str]:
    """
    Return JD requirements that are NOT supported by master resume.
    These would require fake additions to hit 100 ATS.
    """
    inv = _as_inventory(master_inventory)
    allowed = inv.get("skills", set()) | inv.get("tools", set())
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
    master_inventory: Union[CandidateProfile, dict],
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
    inv = _as_inventory(master_inventory)
    jd_keywords = _extract_jd_keywords(jd_text)
    unsupported = get_unsupported_requirements(jd_keywords[:20], inv)
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

    # Auto-apply threshold: fit ≥ 85, ATS ≥ 100, no unsupported JD skills
    FIT_THRESHOLD_AUTO_APPLY = 85
    apply = score >= FIT_THRESHOLD_AUTO_APPLY and ats_score >= 100 and len(unsupported) == 0
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


def is_job_fit(
    profile: CandidateProfile,
    job: Union["JobListing", dict, str],
    ats_score: int = 0,
) -> FitResult:
    """
    Central fit gate: evaluate job against master resume profile.
    job: JobListing, or dict with description/title/company, or raw JD string.
    Returns FitResult with decision (apply/review/reject), score, reasons.
    """
    if isinstance(job, str):
        jd_text = job
    elif hasattr(job, "description"):
        jd_text = job.description
    elif isinstance(job, dict):
        jd_text = job.get("description", job.get("job_description", ""))
    else:
        jd_text = ""

    fit = compute_job_fit_score(jd_text, profile, ats_score=ats_score)
    decision = "apply" if fit["apply"] else ("reject" if fit["reject"] else "review")
    return FitResult(
        decision=decision,
        score=fit["score"],
        reasons=fit["reasons"],
        unsupported_requirements=fit["unsupported_requirements"],
        apply=fit["apply"],
        review=fit["review"],
        reject=fit["reject"],
    )


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
