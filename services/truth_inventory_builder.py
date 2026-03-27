"""
Phase 1 — Structured Truth Inventory Builder
Extracts a rich, structured understanding of the candidate from:
  - master resume text
  - candidate_profile.json
  - project metadata

Output is a TruthInventory dataclass that feeds:
  - fit_engine.py (role/seniority matching)
  - iterative_ats_optimizer.py (keyword truth-checking)
  - queue_runner_executor.py (form answers)
  - resume_designer.py (content selection)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Role family taxonomy (must match fit_engine.py)
# ---------------------------------------------------------------------------

ROLE_FAMILY_KEYWORDS: dict[str, list[str]] = {
    "ai_ml_engineer": [
        "machine learning", "ml engineer", "ai engineer", "applied scientist",
        "model training", "deep learning", "neural network", "pytorch", "tensorflow",
        "scikit", "xgboost", "feature engineering", "model deployment",
    ],
    "genai_engineer": [
        "generative ai", "genai", "llm", "large language model", "gpt", "claude",
        "prompt engineer", "rag", "retrieval augmented", "langchain", "llamaindex",
        "fine-tuning", "embeddings", "vector database", "pinecone", "weaviate",
    ],
    "ai_agent_engineer": [
        "ai agent", "agentic", "multi-agent", "autonomous agent", "tool use",
        "agent framework", "crewai", "autogen", "langgraph", "orchestration",
        "workflow automation", "mcp", "model context protocol",
    ],
    "mlops_engineer": [
        "mlops", "ml platform", "ml infrastructure", "model monitoring",
        "model registry", "mlflow", "kubeflow", "airflow", "feature store",
        "data pipeline", "ci/cd for ml", "model versioning", "drift detection",
    ],
    "data_scientist": [
        "data scientist", "data science", "statistical modeling", "hypothesis testing",
        "a/b testing", "regression", "classification", "clustering", "sql",
        "pandas", "numpy", "matplotlib", "seaborn", "exploratory data analysis",
    ],
    "data_engineer": [
        "data engineer", "etl", "data pipeline", "spark", "kafka", "dbt",
        "airflow", "data warehouse", "snowflake", "bigquery", "redshift",
        "data lake", "stream processing", "batch processing",
    ],
    "software_engineer": [
        "software engineer", "backend", "api development", "rest api", "fastapi",
        "flask", "django", "microservices", "system design", "distributed systems",
    ],
}

# Skill evidence map — maps skill/tool to resume evidence patterns
SKILL_EVIDENCE_PATTERNS: dict[str, list[str]] = {
    "python": ["python", "py", ".py"],
    "pytorch": ["pytorch", "torch"],
    "tensorflow": ["tensorflow", "tf"],
    "scikit-learn": ["scikit", "sklearn"],
    "huggingface": ["hugging face", "huggingface", "transformers"],
    "langchain": ["langchain"],
    "llamaindex": ["llamaindex", "llama_index", "llama index"],
    "openai": ["openai", "gpt-", "chatgpt"],
    "llm": ["llm", "large language model", "large language models", "gpt", "chatgpt", "claude"],
    "genai": ["generative ai", "genai", "gen ai"],
    "mlops": ["mlops", "ml ops", "machine learning operations", "model monitoring", "model registry", "feature store"],
    "deep_learning": ["deep learning", "neural network", "neural networks", "cnn", "lstm"],
    "ci_cd": ["ci/cd", "continuous integration", "continuous deployment", "continuous delivery"],
    "aws": ["aws", "amazon web services", "s3", "ec2", "sagemaker", "lambda"],
    "azure": ["azure", "microsoft azure"],
    "gcp": ["gcp", "google cloud", "bigquery", "vertex"],
    "docker": ["docker", "containeriz"],
    "kubernetes": ["kubernetes", "k8s"],
    "sql": ["sql", "postgres", "mysql", "sqlite", "database"],
    "spark": ["apache spark", "pyspark", "spark"],
    "mlflow": ["mlflow"],
    "airflow": ["airflow"],
    "fastapi": ["fastapi", "fast api"],
    "flask": ["flask"],
    "django": ["django"],
    "react": ["react", "reactjs"],
    "typescript": ["typescript", "ts"],
    "javascript": ["javascript", "js"],
    "git": ["git", "github", "gitlab"],
    "linux": ["linux", "unix", "bash", "shell"],
    "rag": ["rag", "retrieval augmented", "retrieval-augmented"],
    "vector_db": ["pinecone", "weaviate", "chroma", "qdrant", "faiss", "vector store", "vector database"],
    "fine_tuning": ["fine-tun", "finetuning", "fine tuning", "lora", "qlora"],
    "nlp": ["nlp", "natural language processing", "text classification", "named entity", "sentiment"],
    "computer_vision": ["computer vision", "cv", "image classification", "object detection", "cnn"],
    "data_analysis": ["data analysis", "pandas", "numpy", "matplotlib", "seaborn", "eda"],
    "a_b_testing": ["a/b test", "ab test", "experiment", "hypothesis test"],
    "distributed_systems": ["distributed", "microservices", "kafka", "rabbitmq"],
}


# ---------------------------------------------------------------------------
# TruthInventory dataclass
# ---------------------------------------------------------------------------

@dataclass
class TruthInventory:
    # Candidate identity
    full_name: str = ""
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    github: str = ""
    portfolio: str = ""
    location: str = ""

    # Role positioning
    role_families: list[str] = field(default_factory=list)       # e.g. ["ai_ml_engineer", "genai_engineer"]
    primary_role_family: str = ""                                  # strongest match
    seniority_band: str = "entry"                                  # intern/entry/mid/senior/staff_plus
    target_titles: list[str] = field(default_factory=list)

    # Experience evidence
    total_years_experience: float = 0.0
    graduation_year: Optional[int] = None
    skills_supported: list[str] = field(default_factory=list)     # clearly in resume
    skills_partial: list[str] = field(default_factory=list)       # mentioned but shallow
    skills_not_supported: list[str] = field(default_factory=list) # not found

    # Quantified experience by domain
    years_by_domain: dict[str, float] = field(default_factory=dict)  # {"ml": 2.0, "python": 3.0}

    # Short-answer truth values (for form filling)
    years_python: str = ""
    years_ml: str = ""
    years_sql: str = ""
    years_nlp: str = ""
    years_aws: str = ""

    # Work authorization
    visa_status: str = ""
    requires_sponsorship: bool = False
    authorized_us: bool = True
    work_auth_note: str = ""

    # Preferences
    salary_min: int = 0
    salary_max: int = 0
    salary_note: str = ""
    open_to_remote: bool = True
    open_to_hybrid: bool = True
    open_to_relocation: bool = False
    preferred_locations: list[str] = field(default_factory=list)

    # Deployment & production evidence
    has_production_deployment: bool = False
    has_research_publication: bool = False
    has_open_source_contribution: bool = False
    github_projects: list[str] = field(default_factory=list)

    # Hard constraints
    hard_no_keywords: list[str] = field(default_factory=list)  # must not appear in JD
    hard_required_keywords: list[str] = field(default_factory=list)

    # Raw resume sections (for resume designer)
    summary_text: str = ""
    work_experience_text: str = ""
    education_text: str = ""
    projects_text: str = ""
    skills_section_text: str = ""

    # Source metadata
    master_resume_path: str = ""
    profile_path: str = ""
    built_at: str = ""


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_truth_inventory(
    master_resume_text: str = "",
    master_resume_path: Optional[str] = None,
    profile: Optional[dict] = None,
) -> TruthInventory:
    """
    Build a TruthInventory from master resume text + candidate profile.
    This is the single source of truth for all downstream scoring/generation.
    """
    from datetime import datetime

    inv = TruthInventory(built_at=datetime.utcnow().isoformat())

    # Load profile
    if profile is None:
        profile = _load_profile_safe()

    # ------------------------------------------------------------------
    # 1. Identity from profile
    # ------------------------------------------------------------------
    inv.full_name = profile.get("name", "")
    inv.email = profile.get("email", "")
    inv.phone = profile.get("phone", "")
    inv.linkedin = profile.get("linkedin_url", profile.get("linkedin", ""))
    inv.github = profile.get("github_url", profile.get("github", ""))
    inv.portfolio = profile.get("portfolio_url", profile.get("portfolio", ""))
    inv.location = profile.get("location", profile.get("city", ""))

    # ------------------------------------------------------------------
    # 2. Work authorization
    # ------------------------------------------------------------------
    inv.visa_status = profile.get("visa_status", "")
    inv.work_auth_note = profile.get("work_authorization_note", "")
    vs = inv.visa_status.lower()
    inv.requires_sponsorship = any(k in vs for k in ["opt", "h1b", "h-1b", "need", "require"])
    inv.authorized_us = "f-1" in vs or "opt" in vs or "citizen" in vs or "green" in vs or "h1b" in vs

    # ------------------------------------------------------------------
    # 3. Short-answer values
    # ------------------------------------------------------------------
    sa = profile.get("short_answers", {})
    inv.years_python = sa.get("years_python", "")
    inv.years_ml = sa.get("years_ml", "")
    inv.years_sql = sa.get("years_sql", "")
    inv.years_nlp = sa.get("years_nlp", "")
    inv.years_aws = sa.get("years_aws", "")

    # ------------------------------------------------------------------
    # 4. Preferences
    # ------------------------------------------------------------------
    inv.salary_min = int(profile.get("salary_min", 0))
    inv.salary_max = int(profile.get("salary_max", 0))
    inv.salary_note = profile.get("salary_note", "")
    inv.open_to_remote = profile.get("open_to_remote", True)
    inv.open_to_hybrid = profile.get("open_to_hybrid", True)
    inv.open_to_relocation = profile.get("open_to_relocation", False)
    inv.preferred_locations = profile.get("preferred_locations", [])
    inv.target_titles = profile.get("target_titles", [])

    # ------------------------------------------------------------------
    # 5. Graduation year + seniority estimate
    # ------------------------------------------------------------------
    grad_str = profile.get("graduation_date", "")
    if grad_str:
        m = re.search(r"(\d{4})", grad_str)
        if m:
            inv.graduation_year = int(m.group(1))

    inv.seniority_band = _estimate_seniority(inv.graduation_year, master_resume_text)
    inv.total_years_experience = _estimate_years_experience(inv.graduation_year, master_resume_text)

    # ------------------------------------------------------------------
    # 6. Skills evidence from resume text
    # ------------------------------------------------------------------
    if master_resume_text:
        text_lower = master_resume_text.lower()
        for skill, patterns in SKILL_EVIDENCE_PATTERNS.items():
            hits = sum(1 for p in patterns if p.lower() in text_lower)
            if hits >= 2:
                inv.skills_supported.append(skill)
            elif hits == 1:
                inv.skills_partial.append(skill)

        # ------------------------------------------------------------------
        # 7. Role family detection
        # ------------------------------------------------------------------
        family_scores: dict[str, int] = {}
        for family, keywords in ROLE_FAMILY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw.lower() in text_lower)
            if score > 0:
                family_scores[family] = score

        sorted_families = sorted(family_scores, key=lambda k: family_scores[k], reverse=True)
        inv.role_families = sorted_families[:4]
        inv.primary_role_family = sorted_families[0] if sorted_families else "ai_ml_engineer"

        # ------------------------------------------------------------------
        # 8. Production/research evidence
        # ------------------------------------------------------------------
        inv.has_production_deployment = any(kw in text_lower for kw in [
            "deployed", "production", "prod", "million users", "million requests",
            "serving", "inference endpoint", "real-time", "live system",
        ])
        inv.has_research_publication = any(kw in text_lower for kw in [
            "published", "arxiv", "paper", "conference", "workshop", "journal",
            "acl", "emnlp", "neurips", "icml", "cvpr",
        ])
        inv.has_open_source_contribution = any(kw in text_lower for kw in [
            "open source", "open-source", "github.com", "contributor", "pull request",
        ])

        # ------------------------------------------------------------------
        # 9. Extract resume sections (for designer)
        # ------------------------------------------------------------------
        inv.summary_text = _extract_section(master_resume_text, ["summary", "objective", "profile", "about"])
        inv.work_experience_text = _extract_section(master_resume_text, ["experience", "work history", "employment"])
        inv.education_text = _extract_section(master_resume_text, ["education", "academic"])
        inv.projects_text = _extract_section(master_resume_text, ["project", "portfolio"])
        inv.skills_section_text = _extract_section(master_resume_text, ["skills", "technical skills", "competencies"])

    # ------------------------------------------------------------------
    # 10. Years by domain from short answers
    # ------------------------------------------------------------------
    inv.years_by_domain = _parse_years_by_domain(sa, inv.total_years_experience)

    if master_resume_path:
        inv.master_resume_path = str(master_resume_path)

    return inv


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_profile_safe() -> dict:
    try:
        from services.profile_service import load_profile
        return load_profile() or {}
    except Exception:
        profile_path = PROJECT_ROOT / "config" / "candidate_profile.json"
        if profile_path.exists():
            return json.loads(profile_path.read_text())
        return {}


def _estimate_seniority(grad_year: Optional[int], resume_text: str) -> str:
    from datetime import datetime
    current_year = datetime.utcnow().year

    if grad_year:
        years_since_grad = current_year - grad_year
        if years_since_grad < 0:
            return "entry"   # still in school / graduating soon
        elif years_since_grad <= 1:
            return "entry"
        elif years_since_grad <= 3:
            return "entry"   # 0-3 years post-grad = entry/junior
        elif years_since_grad <= 6:
            return "mid"
        elif years_since_grad <= 10:
            return "senior"
        else:
            return "staff_plus"

    # Fallback: look for signals in resume text
    text_lower = (resume_text or "").lower()
    if any(k in text_lower for k in ["staff engineer", "principal", "distinguished", "fellow"]):
        return "staff_plus"
    if any(k in text_lower for k in ["senior software", "senior ml", "senior engineer", "lead engineer", "tech lead"]):
        return "senior"
    if any(k in text_lower for k in ["junior", "associate", "intern", "entry"]):
        return "entry"
    return "mid"


def _estimate_years_experience(grad_year: Optional[int], resume_text: str) -> float:
    from datetime import datetime
    current_year = datetime.utcnow().year

    if grad_year:
        return max(0.0, float(current_year - grad_year))

    # Try to find years from resume text
    if resume_text:
        m = re.search(r"(\d+)\+?\s+years?\s+(?:of\s+)?(?:experience|exp)", resume_text, re.IGNORECASE)
        if m:
            return float(m.group(1))
    return 2.0


def _parse_years_by_domain(short_answers: dict, total_years: float) -> dict:
    """Convert short_answers years to float mapping."""
    result: dict[str, float] = {}
    for key, val in short_answers.items():
        if key.startswith("years_") and val:
            domain = key.replace("years_", "")
            # Parse "3+" → 3.0, "2-4" → 3.0, "3" → 3.0
            digits = re.findall(r"\d+", str(val))
            if digits:
                nums = [float(d) for d in digits]
                result[domain] = sum(nums) / len(nums)
    if not result and total_years:
        result["general"] = total_years
    return result


def _extract_section(text: str, section_names: list[str]) -> str:
    """
    Extract a resume section by scanning for header keywords.
    Returns everything between the matched header and the next all-caps header.
    """
    if not text:
        return ""

    lines = text.split("\n")
    start_idx = None
    end_idx = None

    for i, line in enumerate(lines):
        line_clean = line.strip().lower()
        if any(sn in line_clean for sn in section_names):
            # Check it looks like a header (short line, possibly all-caps)
            if len(line.strip()) < 60:
                start_idx = i
                break

    if start_idx is None:
        return ""

    # Find end: next section header (short all-caps-ish line)
    for i in range(start_idx + 1, len(lines)):
        line_clean = lines[i].strip()
        if len(line_clean) < 50 and line_clean and line_clean == line_clean.upper() and len(line_clean) > 3:
            end_idx = i
            break
        # Also stop at blank line followed by another potential header
    if end_idx is None:
        end_idx = min(start_idx + 60, len(lines))

    return "\n".join(lines[start_idx:end_idx]).strip()


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def truth_inventory_to_dict(inv: TruthInventory) -> dict:
    """JSON-serializable representation for MCP tool responses."""
    return {
        "full_name": inv.full_name,
        "email": inv.email,
        "location": inv.location,
        "role_families": inv.role_families,
        "primary_role_family": inv.primary_role_family,
        "seniority_band": inv.seniority_band,
        "total_years_experience": inv.total_years_experience,
        "target_titles": inv.target_titles,
        "skills_supported": inv.skills_supported,
        "skills_partial": inv.skills_partial,
        "skills_supported_count": len(inv.skills_supported),
        "years_by_domain": inv.years_by_domain,
        "short_answers": {
            "years_python": inv.years_python,
            "years_ml": inv.years_ml,
            "years_sql": inv.years_sql,
            "years_nlp": inv.years_nlp,
            "years_aws": inv.years_aws,
        },
        "visa_status": inv.visa_status,
        "requires_sponsorship": inv.requires_sponsorship,
        "authorized_us": inv.authorized_us,
        "work_auth_note": inv.work_auth_note,
        "salary_min": inv.salary_min,
        "salary_max": inv.salary_max,
        "open_to_remote": inv.open_to_remote,
        "open_to_relocation": inv.open_to_relocation,
        "has_production_deployment": inv.has_production_deployment,
        "has_research_publication": inv.has_research_publication,
        "has_open_source_contribution": inv.has_open_source_contribution,
        "hard_no_keywords": inv.hard_no_keywords,
        "built_at": inv.built_at,
    }
