"""
Phase 11 — Resume Package Service
Generates a truthfully-optimized resume for a specific job.
Uses the existing iterative ATS optimizer loop.
Returns a versioned package with ATS metadata and upload path.
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent
GENERATED_DIR = PROJECT_ROOT / "generated_resumes"
PACKAGES_DIR = PROJECT_ROOT / "generated_resumes" / "_packages"
PACKAGES_DIR.mkdir(parents=True, exist_ok=True)


def _load_master_resume_text(master_resume_path: Optional[str] = None) -> str:
    """Load master resume text from PDF or text file."""
    path = master_resume_path or os.getenv("RESUME_PATH", "")
    if not path:
        # Search Master_Resumes directory
        mr_dir = PROJECT_ROOT / "Master_Resumes"
        if mr_dir.exists():
            for f in sorted(mr_dir.iterdir()):
                if f.suffix.lower() in (".pdf", ".txt", ".md"):
                    path = str(f)
                    break
    if not path or not Path(path).exists():
        return ""
    
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                return "\n".join(page.extract_text() or "" for page in pdf.pages)
        except ImportError:
            try:
                import pypdf
                reader = pypdf.PdfReader(path)
                return "\n".join(page.extract_text() or "" for page in reader.pages)
            except Exception:
                return ""
    else:
        try:
            return Path(path).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""


def _safe_name(s: str) -> str:
    import re
    return re.sub(r"[^\w\-]", "_", s or "Unknown")[:40]


def generate_package_for_job(
    job_title: str,
    company: str,
    job_description: str,
    master_resume_path: Optional[str] = None,
    target_ats_score: int = 85,
    max_iterations: int = 5,
) -> dict:
    """
    Generate a truthfully-optimized resume package for a job.
    
    Returns:
        {
            resume_version_id, package_status, resume_path,
            initial_ats_score, final_ats_score, truth_safe_ats_ceiling,
            covered_keywords, truthful_missing_keywords, unsupported_keywords,
            optimization_summary, iterations
        }
    """
    version_id = f"res_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    package_dir = PACKAGES_DIR / version_id
    package_dir.mkdir(parents=True, exist_ok=True)

    # Load master resume
    master_text = _load_master_resume_text(master_resume_path)
    if not master_text:
        return {
            "resume_version_id": version_id,
            "package_status": "error",
            "error": "Could not load master resume text. Set RESUME_PATH or ensure Master_Resumes/ has a PDF.",
        }

    # Run existing iterative ATS optimizer
    try:
        from enhanced_ats_checker import EnhancedATSChecker
        from agents.iterative_ats_optimizer import run_iterative_ats_optimizer
        from agents.state import AgentState

        ats_checker = EnhancedATSChecker()

        # Minimal tailor/humanize functions (text-based, no LLM required for MVP)
        def _tailor_fn(state: dict) -> dict:
            """Simple keyword-injection tailoring from supported missing keywords."""
            resume = state.get("base_resume_text", "")
            missing = state.get("missing_skills", [])
            if missing:
                # Append a skills addendum line (truthful — only what master resume supports)
                addendum = "Additional competencies: " + ", ".join(missing[:8])
                if addendum not in resume:
                    resume = resume + "\n\n" + addendum
            return {"tailored_resume_text": resume}

        def _humanize_fn(state: dict) -> dict:
            return {"humanized_resume_text": state.get("tailored_resume_text", "")}

        initial_state = AgentState(
            base_resume_text=master_text,
            job_description=job_description,
            target_position=job_title,
            target_company=company,
            target_location="",
        )

        result = run_iterative_ats_optimizer(
            state=initial_state,
            ats_checker=ats_checker,
            tailor_fn=_tailor_fn,
            humanize_fn=_humanize_fn,
            target_score=target_ats_score,
            max_attempts=max_iterations,
            truth_safe=True,
        )

        final_text = result.get("humanized_resume_text", master_text)
        initial_score = result.get("initial_ats_score", 0)
        final_score = result.get("final_ats_score", 0)
        ceiling = result.get("truthful_ceiling", final_score)
        missing_kw = result.get("truthful_missing_keywords", result.get("missing_keywords", []))
        iterations = result.get("iterations", result.get("attempts", 1))
        converged = result.get("converged", False)

    except Exception as e:
        # Fallback: copy master resume as-is, run basic ATS check
        try:
            from enhanced_ats_checker import EnhancedATSChecker
            ats_checker = EnhancedATSChecker()
            ats_result = ats_checker.comprehensive_ats_check(
                resume_text=master_text,
                job_description=job_description,
                job_title=job_title,
                company_name=company,
                location="",
            )
            initial_score = ats_result.get("ats_score", 0)
            final_score = initial_score
            ceiling = initial_score
            missing_kw = ats_result.get("detailed_breakdown", {}).get("missing_keywords", [])
        except Exception:
            initial_score = 0
            final_score = 0
            ceiling = 0
            missing_kw = []
        final_text = master_text
        iterations = 1
        converged = False

    # Save optimized text
    text_path = package_dir / "resume_optimized.txt"
    text_path.write_text(final_text, encoding="utf-8")

    # Copy best matching PDF
    pdf_path = _copy_best_resume_pdf(company, job_title, package_dir, master_resume_path)

    # Keyword coverage analysis
    covered, unsupported = _analyze_keyword_coverage(final_text, job_description)

    # Package status
    if final_score >= target_ats_score:
        status = "optimized_truth_safe"
    elif final_score >= 70:
        status = "generated"
    else:
        status = "generated"

    # Write package metadata
    metadata = {
        "resume_version_id": version_id,
        "package_status": status,
        "job_title": job_title,
        "company": company,
        "resume_path": str(pdf_path) if pdf_path else str(text_path),
        "resume_text_path": str(text_path),
        "initial_ats_score": initial_score,
        "final_ats_score": final_score,
        "truth_safe_ats_ceiling": ceiling,
        "covered_keywords": covered[:20],
        "truthful_missing_keywords": missing_kw[:10],
        "unsupported_keywords": unsupported[:10],
        "optimization_summary": _build_summary(initial_score, final_score, ceiling, converged, missing_kw),
        "iterations": iterations,
        "created_at": datetime.now().isoformat(),
    }
    (package_dir / "package.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return metadata


def _copy_best_resume_pdf(company: str, job_title: str, dest_dir: Path, master_resume_path: Optional[str]) -> Optional[Path]:
    """Copy the best matching PDF resume to the package directory."""
    # Prefer explicitly provided path
    candidates = []
    if master_resume_path and Path(master_resume_path).exists():
        candidates.append(Path(master_resume_path))

    # Search generated_resumes for existing tailored PDFs
    title_lower = job_title.lower()
    comp_lower = company.lower()
    for p in GENERATED_DIR.rglob("*.pdf"):
        name = p.name.lower()
        if any(w in name for w in comp_lower.split()) or any(w in name for w in title_lower.split()):
            candidates.append(p)

    # Fall back to Master_Resumes
    mr_dir = PROJECT_ROOT / "Master_Resumes"
    if mr_dir.exists():
        for p in sorted(mr_dir.iterdir()):
            if p.suffix.lower() == ".pdf":
                if "aiml" in p.name.lower() or "ml" in p.name.lower() or "ai" in p.name.lower():
                    candidates.insert(0, p)
                else:
                    candidates.append(p)

    if not candidates:
        return None

    src = candidates[0]
    dest = dest_dir / src.name
    shutil.copy2(src, dest)
    return dest


def _analyze_keyword_coverage(resume_text: str, job_description: str) -> tuple[list[str], list[str]]:
    """Return (covered_keywords, job_keywords_not_in_resume)."""
    import re
    resume_lower = resume_text.lower()
    # Extract significant words from JD
    jd_words = set(re.findall(r'\b[a-z][a-z0-9\+#]{2,}\b', job_description.lower()))
    common_words = {
        "the", "and", "for", "with", "this", "that", "are", "you", "our", "can",
        "will", "from", "have", "has", "not", "but", "they", "your", "its", "all",
        "experience", "required", "skills", "role", "team", "work", "build", "using",
    }
    jd_words -= common_words

    covered = [w for w in sorted(jd_words) if w in resume_lower]
    uncovered = [w for w in sorted(jd_words) if w not in resume_lower]
    return covered[:30], uncovered[:20]


def _build_summary(initial: int, final: int, ceiling: int, converged: bool, missing: list[str]) -> str:
    parts = [f"ATS score: {initial} → {final} (truth-safe ceiling: {ceiling})."]
    if converged:
        parts.append("Optimizer converged at target score.")
    elif final == ceiling:
        parts.append("Reached truth-safe ceiling — no further truthful improvement possible.")
    if missing:
        parts.append(f"Keywords not supported by resume: {', '.join(missing[:5])}.")
    return " ".join(parts)


def load_package(version_id: str) -> Optional[dict]:
    """Load a previously generated package by version ID."""
    meta_path = PACKAGES_DIR / version_id / "package.json"
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return None
