"""
Job-specific resume PDF path (MCP ``prepare_resume_for_job`` parity).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict


def prepare_resume_for_job_payload(
    job_title: str,
    company: str,
    resume_source_path: str = "",
) -> Dict[str, Any]:
    try:
        from services.resume_naming import ensure_resume_exists_for_job

        project_root = Path(__file__).resolve().parent.parent
        job = {"title": job_title, "company": company}
        path = ensure_resume_exists_for_job(
            job,
            resume_content_path=resume_source_path or os.getenv("RESUME_PATH"),
            output_dir=str(project_root / "generated_resumes"),
        )
        if path:
            return {"resume_path": path, "filename": os.path.basename(path), "status": "ready"}
        return {
            "resume_path": "",
            "filename": "",
            "status": "no_source",
            "message": "No resume found. Add PDF to Master_Resumes/ or set RESUME_PATH.",
        }
    except Exception as e:
        return {"resume_path": "", "status": "error", "message": str(e)[:200]}
