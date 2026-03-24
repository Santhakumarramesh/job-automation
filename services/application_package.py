"""
Full application package for manual-assist lane (MCP ``prepare_application_package`` parity).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict


def prepare_application_package_payload(
    job_title: str,
    company: str,
    job_description: str = "",
    master_resume_text: str = "",
    job_location: str = "",
    work_type: str = "",
) -> Dict[str, Any]:
    try:
        from agents.application_answerer import answer_question_structured
        from services.address_for_job import get_address_for_job as resolve_address
        from services.profile_service import load_profile
        from services.resume_naming import ensure_resume_exists_for_job

        project_root = Path(__file__).resolve().parent.parent
        profile = load_profile()
        job = {
            "title": job_title,
            "company": company,
            "description": job_description,
            "location": job_location,
            "work_type": work_type,
        }
        addr = resolve_address(job, profile)
        resume_path = ensure_resume_exists_for_job(
            job,
            resume_content_path=os.getenv("RESUME_PATH"),
            output_dir=str(project_root / "generated_resumes"),
        )
        jc = {"company": company, "title": job_title}
        sp = answer_question_structured("Do you require sponsorship?", profile=profile, job_context=jc)
        wr = answer_question_structured("Why this role?", profile=profile, job_context=jc)
        wc = answer_question_structured("Why this company?", profile=profile, job_context=jc)
        values = {
            "first_name": (profile.get("full_name", "") or "").split()[0] or "",
            "last_name": " ".join((profile.get("full_name", "") or "").split()[1:]) or "",
            "email": profile.get("email", ""),
            "phone": profile.get("phone", ""),
            "linkedin_url": profile.get("linkedin_url", ""),
            "github_url": profile.get("github_url", ""),
            "work_authorization": profile.get("work_authorization_note", ""),
            "mailing_address_oneline": addr.get("mailing_address_oneline", ""),
            "sponsorship": sp["answer"],
            "why_this_role": wr["answer"],
            "why_this_company": wc["answer"],
        }
        answer_review = {
            "sponsorship": {
                "manual_review_required": sp["manual_review_required"],
                "reason_codes": sp["reason_codes"],
                "classified_type": sp["classified_type"],
            },
            "why_this_role": {
                "manual_review_required": wr["manual_review_required"],
                "reason_codes": wr["reason_codes"],
                "classified_type": wr["classified_type"],
            },
            "why_this_company": {
                "manual_review_required": wc["manual_review_required"],
                "reason_codes": wc["reason_codes"],
                "classified_type": wc["classified_type"],
            },
        }
        fit_result: Dict[str, Any] = {}
        if job_description and master_resume_text:
            from services.ats_service import check_fit_gate

            state = {
                "base_resume_text": master_resume_text,
                "job_description": job_description,
                "target_position": job_title,
                "target_company": company,
                "target_location": "USA",
            }
            fit_result = check_fit_gate(state)
        return {
            "status": "ok",
            "resume_path": resume_path or "",
            "autofill_values": values,
            "address_selection": {
                "address_label": addr.get("address_label", "default"),
                "used_alternate": addr.get("used_alternate", False),
                "selection_reason": addr.get("selection_reason", ""),
                "mailing_address": addr.get("mailing_address", {}),
            },
            "answer_review": answer_review,
            "fit_decision": fit_result.get("fit_decision", ""),
            "job_fit_score": fit_result.get("job_fit_score", 0),
            "unsupported_requirements": fit_result.get("unsupported_requirements", []),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}
