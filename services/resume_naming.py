"""
Resume naming for job applications. Produces paths like:
  {Name}_{Position}_at_{Company}_Resume.pdf
Used by application runner and MCP autofill server.
"""

import os
import re
from pathlib import Path
from typing import Optional


def sanitize_filename_part(s: str, max_len: int = 40) -> str:
    """Sanitize for filename: alphanumeric, underscore, hyphen."""
    s = re.sub(r"[^\w\s-]", "", str(s or ""))
    s = re.sub(r"[-\s]+", "_", s.strip())
    return s[:max_len] if s else "Unknown"


def resume_filename_for_job(
    job: dict,
    candidate_name: str = "",
    suffix: str = "Resume",
    ext: str = "pdf",
) -> str:
    """
    Generate resume filename for job application.
    Format: {Name}_{Position}_at_{Company}_{Suffix}.{ext}
    Example: John_Doe_ML_Engineer_at_OpenAI_Resume.pdf
    """
    name = candidate_name or os.getenv("CANDIDATE_NAME", "Candidate")
    pos = job.get("title") or job.get("jobTitle") or job.get("position", "Role")
    comp = job.get("company") or job.get("companyName", "")
    name_s = sanitize_filename_part(name, 25)
    pos_s = sanitize_filename_part(pos, 35)
    comp_s = sanitize_filename_part(comp, 35)
    base = f"{name_s}_{pos_s}_at_{comp_s}_{suffix}"
    return f"{base}.{ext}"


def resume_path_for_job(
    job: dict,
    output_dir: str = "generated_resumes",
    candidate_name: str = "",
) -> Path:
    """
    Full path for job resume. Creates company subdir.
    Returns: generated_resumes/{Company}/{Name}_{Position}_at_{Company}_Resume.pdf
    """
    comp = job.get("company") or job.get("companyName", "Company")
    comp_s = sanitize_filename_part(comp, 40)
    base = Path(output_dir) / comp_s
    base.mkdir(parents=True, exist_ok=True)
    filename = resume_filename_for_job(job, candidate_name, suffix="Resume", ext="pdf")
    return base / filename


def ensure_resume_exists_for_job(
    job: dict,
    resume_content_path: Optional[str] = None,
    candidate_name: str = "",
    output_dir: str = "generated_resumes",
) -> Optional[str]:
    """
    Ensure a resume exists at the job-specific path.
    If resume_content_path is provided and is a PDF, copies/renames to job path.
    If resume_content_path is a tailored resume from pipeline, use it.
    Returns path string or None if no source resume.
    """
    target = resume_path_for_job(job, output_dir, candidate_name)
    if target.exists():
        return str(target)
    if resume_content_path and os.path.isfile(resume_content_path):
        import shutil
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(resume_content_path, target)
        return str(target)
    # Fallback: find any PDF in Master_Resumes
    proj = Path(__file__).resolve().parent.parent
    for base in [proj / "Master_Resumes", proj / "generated_resumes"]:
        if base.exists():
            for f in base.rglob("*.pdf"):
                target.parent.mkdir(parents=True, exist_ok=True)
                import shutil
                shutil.copy2(f, target)
                return str(target)
    return None
