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


def _resolve_project_file(proj: Path, raw: str) -> Optional[Path]:
    """Absolute path if ``raw`` is an existing file (supports relative-to-project and ~)."""
    s = str(raw or "").strip()
    if not s:
        return None
    p = Path(s).expanduser()
    if not p.is_absolute():
        p = (proj / p).resolve()
    return p if p.is_file() else None


def _pdf_sort_key(path: Path) -> str:
    return str(path).lower()


def _preference_rank(filename_lower: str) -> tuple:
    """Lower tuple sorts first = more preferred master-style names."""
    hints = ("master", "base_resume", "base-resume", "canonical", "primary")
    for i, h in enumerate(hints):
        if h in filename_lower:
            return (i, filename_lower)
    return (len(hints), filename_lower)


def pick_fallback_resume_pdf(project_root: Optional[Path] = None) -> Optional[Path]:
    """
    Deterministic PDF to use when no explicit resume path exists.
    Order: ``MASTER_RESUME_PDF`` / ``DEFAULT_RESUME_PDF`` env, then ``Master_Resumes``
    (name hints like *master* before others, then lexicographic path), then
    ``generated_resumes`` (lexicographic path only — last resort).
    """
    proj = project_root or Path(__file__).resolve().parent.parent
    for key in ("MASTER_RESUME_PDF", "DEFAULT_RESUME_PDF"):
        hit = _resolve_project_file(proj, os.getenv(key, ""))
        if hit and hit.suffix.lower() == ".pdf":
            return hit
    master_dir = proj / "Master_Resumes"
    if master_dir.is_dir():
        pdfs = [p for p in master_dir.rglob("*.pdf") if p.is_file()]
        if pdfs:
            pdfs.sort(key=lambda p: (_preference_rank(p.name.lower()), _pdf_sort_key(p)))
            return pdfs[0]
    gen_dir = proj / "generated_resumes"
    if gen_dir.is_dir():
        pdfs = [p for p in gen_dir.rglob("*.pdf") if p.is_file()]
        if pdfs:
            pdfs.sort(key=_pdf_sort_key)
            return pdfs[0]
    return None


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
    import shutil

    target = resume_path_for_job(job, output_dir, candidate_name)
    if target.exists():
        return str(target)
    if resume_content_path and os.path.isfile(resume_content_path):
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(resume_content_path, target)
        return str(target)
    proj = Path(__file__).resolve().parent.parent
    fb = pick_fallback_resume_pdf(proj)
    if fb:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fb, target)
        return str(target)
    return None
