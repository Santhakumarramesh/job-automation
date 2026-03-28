"""
Recruiter follow-up drafts (MCP ``generate_recruiter_followup`` parity).
"""

from __future__ import annotations

import json
from typing import Any, Dict

from services import model_router


def generate_recruiter_followup_payload(
    job_title: str,
    company: str,
    application_date: str = "",
) -> Dict[str, Any]:
    try:
        from services.profile_service import load_profile

        profile = load_profile()
        name = profile.get("full_name", "Candidate")
        date = application_date or "recently"
        prompt = f"""Generate two brief professional follow-ups for a job applicant.
- Applicant: {name}
- Role: {job_title} at {company}
- Applied: {date}

1. LinkedIn message (2-3 sentences, max 200 chars): polite, reference the role, express continued interest.
2. Email subject + body (2-3 sentences): similar tone, professional.

Return as JSON: {{"linkedin_message": "...", "email_subject": "...", "email_body": "..."}}
"""
        out = model_router.generate_json(
            prompt=prompt,
            system_prompt="You write concise professional recruiter follow-ups.",
            task="reasoning",
            temperature=0.4,
            max_tokens=320,
            required_keys=("linkedin_message", "email_subject", "email_body"),
        )
        data = out.get("data") if out.get("status") == "ok" else {}
        if not isinstance(data, dict):
            data = {}
        text_fallback = json.dumps(data)[:200] if data else ""
        data.setdefault("linkedin_message", text_fallback)
        data.setdefault("email_subject", f"Following up - {job_title}")
        data.setdefault("email_body", text_fallback)
        return {"status": "ok", **data}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}
