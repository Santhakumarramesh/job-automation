"""
Profile-derived autofill field suggestions (MCP ``get_autofill_values`` + REST parity).
"""

from __future__ import annotations

import os
from typing import Any, Dict


def get_autofill_values_payload(
    form_type: str = "linkedin",
    question_hints: str = "",
) -> dict[str, Any]:
    """
    Returns ``{status, values, answer_review?}`` or ``no_profile`` / ``error``.
    ``form_type`` is reserved for future board-specific shaping (linkedin, greenhouse, …).
    """
    try:
        from agents.application_answerer import answer_question_structured
        from services.profile_service import load_profile

        board = (form_type or "linkedin").strip().lower() or "linkedin"
        if board not in ("linkedin", "greenhouse", "lever", "workday", "generic"):
            board = "generic"
        profile = load_profile()
        if not profile:
            return {
                "status": "no_profile",
                "message": "Copy config/candidate_profile.example.json to candidate_profile.json",
            }

        values = {
            "first_name": (profile.get("full_name", "") or "").split()[0] or "",
            "last_name": " ".join((profile.get("full_name", "") or "").split()[1:])
            or (profile.get("full_name", "") or "").split()[0]
            or "",
            "email": profile.get("email", "") or os.getenv("LINKEDIN_EMAIL", ""),
            "phone": profile.get("phone", "") or os.getenv("PHONE", ""),
            "linkedin_url": profile.get("linkedin_url", ""),
            "github_url": profile.get("github_url", ""),
            "portfolio_url": profile.get("portfolio_url", ""),
            "work_authorization": profile.get("work_authorization_note", "") or "",
            "relocation": profile.get("relocation_preference", ""),
            "salary": profile.get("salary_expectation_rule", "Negotiable"),
            "availability": profile.get("notice_period", "Immediate") or "Immediate",
        }

        review_flags: Dict[str, Any] = {}
        if question_hints:
            hints = [h.strip() for h in question_hints.split(",") if h.strip()]
            job_ctx = {"company": "", "title": ""}
            for hint in hints:
                meta = answer_question_structured(hint, profile=profile, job_context=job_ctx)
                key = f"q_{hint[:30]}"
                if meta["answer"]:
                    values[key] = meta["answer"][:150]
                review_flags[key] = {
                    "manual_review_required": meta["manual_review_required"],
                    "reason_codes": meta["reason_codes"],
                    "classified_type": meta["classified_type"],
                }

        return {"status": "ok", "values": values, "answer_review": review_flags}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}
