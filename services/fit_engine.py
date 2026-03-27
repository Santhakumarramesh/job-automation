"""
Phase 11 — Structured Fit Engine
Scores jobs against the candidate's truth inventory using:
  • role family match
  • seniority band match
  • experience evidence match
  • requirement evidence mapping (supported / partially_supported / unsupported / manual_review)
  • hard blockers

Replaces shallow keyword-overlap gating with explainable, evidence-based scoring.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Role family taxonomy
# ---------------------------------------------------------------------------

ROLE_FAMILIES: dict[str, list[str]] = {
    "ai_ml_engineer": [
        "ai engineer", "ml engineer", "machine learning engineer", "ai/ml", "ml/ai",
        "artificial intelligence engineer", "applied ml", "ai software engineer",
        "deep learning engineer", "computer vision engineer",
    ],
    "genai_engineer": [
        "genai", "generative ai", "llm engineer", "rag engineer", "prompt engineer",
        "ai application engineer", "foundation model", "chatbot engineer",
    ],
    "data_scientist": [
        "data scientist", "research scientist", "applied scientist", "quantitative analyst",
        "machine learning scientist", "statistician", "ml researcher",
    ],
    "mlops_engineer": [
        "mlops", "ml platform", "ml infrastructure", "ai platform", "model ops",
        "machine learning platform", "ai infrastructure", "feature store",
    ],
    "data_engineer": [
        "data engineer", "analytics engineer", "etl developer", "data pipeline",
        "dbt developer", "warehouse engineer",
    ],
    "software_engineer_ai": [
        "software engineer", "backend engineer", "full stack", "platform engineer",
        "swe", "software developer",
    ],
    "ai_agent_engineer": [
        "ai agent", "agentic", "autonomous agent", "multi-agent", "agent engineer",
        "ai automation engineer", "workflow automation",
    ],
}

CANDIDATE_ROLE_FAMILIES = ["ai_ml_engineer", "genai_engineer", "ai_agent_engineer", "mlops_engineer", "data_scientist"]

# ---------------------------------------------------------------------------
# Seniority bands
# ---------------------------------------------------------------------------

SENIORITY_BANDS = {
    "intern": ["intern", "co-op", "coop", "student"],
    "entry": ["entry", "junior", "jr.", "jr ", "associate ", "graduate", "new grad", "entry-level", "0-2 years"],
    "mid": ["mid", "ii", " 2", " 3", "3+", "2-4 years", "3-5 years", "2+ years", "3+ years"],
    "senior": ["senior", "sr.", "sr ", "lead", "staff", "principal", "4+ years", "5+ years", "5-7", "4-6"],
    "staff_plus": ["staff", "principal", "distinguished", "architect", "director", "vp of", "head of"],
}

# ---------------------------------------------------------------------------
# Key evidence signals from master resume
# ---------------------------------------------------------------------------

SKILL_EVIDENCE_MAP: dict[str, list[str]] = {
    "python": ["python"],
    "pytorch": ["pytorch", "torch"],
    "tensorflow": ["tensorflow", "tf"],
    "langchain": ["langchain", "lang chain"],
    "langgraph": ["langgraph"],
    "rag": ["rag", "retrieval-augmented", "retrieval augmented"],
    "llm": ["llm", "gpt", "openai", "claude", "gemini", "mistral", "llama"],
    "vector_db": ["faiss", "pinecone", "weaviate", "chromadb", "qdrant", "milvus"],
    "mlflow": ["mlflow", "ml flow"],
    "fastapi": ["fastapi", "fast api"],
    "aws": ["aws", "amazon web services", "s3", "ec2", "sagemaker", "lambda"],
    "docker": ["docker", "container"],
    "kubernetes": ["kubernetes", "k8s"],
    "sql": ["sql", "postgres", "mysql", "snowflake", "bigquery"],
    "spark": ["spark", "pyspark"],
    "airflow": ["airflow", "dag"],
    "transformers": ["transformers", "huggingface", "hugging face"],
    "nlp": ["nlp", "natural language", "text classification", "ner", "named entity"],
    "computer_vision": ["computer vision", "cv", "object detection", "yolo", "cnn"],
    "deployment": ["deployment", "production", "prod", "serving", "inference", "deploy"],
    "api": ["api", "rest", "graphql", "endpoint"],
    "git": ["git", "github", "version control"],
}


@dataclass
class RequirementEvidence:
    requirement: str
    status: str  # supported | partially_supported | unsupported | manual_review
    evidence: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class FitResult:
    role_family: str
    seniority_band: str
    role_match_score: int       # 0-100
    experience_match_score: int # 0-100
    seniority_match_score: int  # 0-100
    overall_fit_score: int      # 0-100
    fit_decision: str           # apply | review_fit | skip
    fit_reasons: list[str]
    unsupported_requirements: list[str]
    hard_blockers: list[str]
    requirement_evidence_map: list[RequirementEvidence]
    supported_skills: list[str]
    missing_skills: list[str]


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def detect_role_family(job_title: str, job_description: str = "") -> str:
    """Detect job's role family from title + description."""
    text = (job_title + " " + job_description[:500]).lower()
    best_family = "software_engineer_ai"
    best_score = 0
    for family, keywords in ROLE_FAMILIES.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > best_score:
            best_score = score
            best_family = family
    return best_family


def detect_seniority_band(job_title: str, job_description: str = "") -> str:
    """Detect required seniority from title + description."""
    text = (job_title + " " + job_description[:400]).lower()
    # Check from most senior to least
    for band in ["staff_plus", "senior", "mid", "entry", "intern"]:
        kws = SENIORITY_BANDS[band]
        if any(kw in text for kw in kws):
            return band
    return "mid"  # default assumption


def detect_candidate_seniority(resume_text: str, profile: Optional[dict] = None) -> str:
    """Estimate candidate seniority from resume + profile."""
    # Try to extract years from profile
    years = 0
    if profile:
        grad_date = profile.get("graduation_date", "")
        if grad_date:
            try:
                from datetime import datetime
                grad_year = int(str(grad_date)[:4])
                current_year = datetime.now().year
                years = max(0, current_year - grad_year)
            except Exception:
                pass

    # Fall back to resume text patterns
    if years == 0:
        patterns = [
            r"(\d+)\+?\s*years?\s*(?:of\s*)?experience",
            r"experience[:\s]+(\d+)\+?\s*years?",
        ]
        for pat in patterns:
            m = re.search(pat, resume_text[:3000], re.I)
            if m:
                try:
                    years = int(m.group(1))
                    break
                except Exception:
                    pass

    if years <= 1:
        return "entry"
    elif years <= 3:
        return "mid"
    elif years <= 6:
        return "senior"
    else:
        return "staff_plus"


def extract_supported_skills(resume_text: str) -> set[str]:
    """Extract which skills from SKILL_EVIDENCE_MAP are evidenced in the resume."""
    text_lower = resume_text.lower()
    supported = set()
    for skill_key, patterns in SKILL_EVIDENCE_MAP.items():
        if any(p in text_lower for p in patterns):
            supported.add(skill_key)
    return supported


def map_requirements(job_description: str, supported_skills: set[str], resume_text: str) -> list[RequirementEvidence]:
    """Map JD requirements to evidence in the resume."""
    evidence_list: list[RequirementEvidence] = []
    resume_lower = resume_text.lower()
    jd_lower = job_description.lower()

    # Extract hard requirements from JD (lines with "required", "must have", "minimum")
    hard_req_patterns = [
        r"(\d+\+?\s*years?\s+(?:of\s+)?(?:experience\s+)?(?:with|in)\s+[\w\s/,]+)",
        r"(bachelor['\u2019]?s|master['\u2019]?s|ph\.?d\.?)\s+(?:degree\s+)?(?:in\s+[\w\s]+)?",
        r"(?:required|must\s+have|minimum)[:\s]+([^\n.]{10,80})",
        r"(\d+\+?\s*years?\s+[a-z\s]+(?:experience|exp))",
    ]

    seen_reqs: set[str] = set()
    for pat in hard_req_patterns:
        for m in re.finditer(pat, jd_lower, re.I):
            req_text = m.group(0).strip()
            if req_text in seen_reqs or len(req_text) < 8:
                continue
            seen_reqs.add(req_text)

            # Check evidence
            skill_hits = [s for s in supported_skills if any(p in req_text for p in SKILL_EVIDENCE_MAP.get(s, [s]))]
            req_text_in_resume = any(
                w in resume_lower
                for w in re.findall(r'\b[a-z]{3,}\b', req_text)
                if len(w) > 3
            )

            if skill_hits:
                status = "supported"
                conf = 0.9
                ev = skill_hits[:3]
            elif req_text_in_resume:
                status = "partially_supported"
                conf = 0.6
                ev = ["found in resume text"]
            else:
                status = "unsupported"
                conf = 0.0
                ev = []

            evidence_list.append(RequirementEvidence(
                requirement=req_text[:120],
                status=status,
                evidence=ev,
                confidence=conf,
            ))

    # Map skill-specific JD mentions
    for skill_key, patterns in SKILL_EVIDENCE_MAP.items():
        for p in patterns:
            if p in jd_lower:
                if skill_key in supported_skills:
                    ev = RequirementEvidence(
                        requirement=f"Skill: {skill_key}",
                        status="supported",
                        evidence=[f"Found '{p}' in resume"],
                        confidence=0.85,
                    )
                else:
                    ev = RequirementEvidence(
                        requirement=f"Skill: {skill_key}",
                        status="unsupported",
                        evidence=[],
                        confidence=0.0,
                    )
                # Avoid duplicates
                if not any(e.requirement == ev.requirement for e in evidence_list):
                    evidence_list.append(ev)
                break

    return evidence_list


def score_structured_fit(
    job_title: str,
    job_description: str,
    resume_text: str,
    profile: Optional[dict] = None,
    ats_score: int = 0,
) -> FitResult:
    """
    Main entry point. Returns a FitResult with structured, explainable scores.
    """
    profile = profile or {}

    # Detect role family + seniority
    job_family = detect_role_family(job_title, job_description)
    job_seniority = detect_seniority_band(job_title, job_description)
    candidate_seniority = detect_candidate_seniority(resume_text, profile)

    # Role family match score
    candidate_families = CANDIDATE_ROLE_FAMILIES
    role_match = 85 if job_family in candidate_families else 40
    fit_reasons = []

    if job_family in candidate_families:
        fit_reasons.append(f"Role family '{job_family}' aligns with candidate specialization")
    else:
        fit_reasons.append(f"Role family '{job_family}' is outside primary candidate focus areas")

    # Seniority match
    seniority_order = ["intern", "entry", "mid", "senior", "staff_plus"]
    cand_idx = seniority_order.index(candidate_seniority)
    job_idx = seniority_order.index(job_seniority)
    gap = abs(cand_idx - job_idx)
    seniority_match = max(0, 100 - gap * 20)

    if gap == 0:
        fit_reasons.append(f"Seniority '{job_seniority}' matches candidate band '{candidate_seniority}'")
    elif gap == 1:
        fit_reasons.append(f"Seniority gap of 1 band (job: {job_seniority}, candidate: {candidate_seniority}) — likely manageable")
    else:
        fit_reasons.append(f"Seniority gap of {gap} bands (job: {job_seniority}, candidate: {candidate_seniority}) — flag for review")

    # Experience evidence match
    supported_skills = extract_supported_skills(resume_text)
    req_evidence = map_requirements(job_description, supported_skills, resume_text)

    supported_count = sum(1 for r in req_evidence if r.status == "supported")
    partial_count = sum(1 for r in req_evidence if r.status == "partially_supported")
    unsupported_count = sum(1 for r in req_evidence if r.status == "unsupported")
    total = max(1, supported_count + partial_count + unsupported_count)

    exp_match = int(((supported_count + 0.5 * partial_count) / total) * 100)
    exp_match = min(95, max(10, exp_match))

    # ATS contribution
    ats_contribution = int(ats_score * 0.3) if ats_score else 0

    # Overall fit
    overall = int(
        role_match * 0.35 +
        seniority_match * 0.25 +
        exp_match * 0.25 +
        ats_contribution * 0.15
    )

    # Hard blockers
    hard_blockers: list[str] = []
    jd_lower = job_description.lower()
    blocking_phrases = [
        ("security clearance", "requires security clearance"),
        ("active clearance", "requires active clearance"),
        ("us citizen only", "requires US citizenship only"),
        ("15+ years", "requires 15+ years experience"),
        ("phd required", "PhD required"),
        ("must be located in", "location restriction"),
    ]
    for phrase, label in blocking_phrases:
        if phrase in jd_lower:
            hard_blockers.append(label)

    # Fit decision
    unsupported_reqs = [r.requirement for r in req_evidence if r.status == "unsupported"]
    missing_skills = list(set(SKILL_EVIDENCE_MAP.keys()) - supported_skills)
    supported_skills_list = list(supported_skills)

    if hard_blockers:
        decision = "skip"
        fit_reasons.append(f"Hard blockers: {'; '.join(hard_blockers)}")
    elif overall >= 70 and gap <= 1 and not hard_blockers:
        decision = "apply"
    elif overall >= 55:
        decision = "review_fit"
        fit_reasons.append("Moderate fit — manual review recommended")
    else:
        decision = "skip"
        fit_reasons.append("Low overall fit score")

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
        supported_skills=supported_skills_list,
        missing_skills=missing_skills[:15],
    )


def fit_result_to_dict(r: FitResult) -> dict:
    """Serialize FitResult to JSON-safe dict."""
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
