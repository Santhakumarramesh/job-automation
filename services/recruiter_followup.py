"""
Recruiter follow-up drafts (MCP ``generate_recruiter_followup`` parity).
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict


def generate_recruiter_followup_payload(
    job_title: str,
    company: str,
    application_date: str = "",
) -> Dict[str, Any]:
    try:
        from langchain_core.messages import HumanMessage
        from langchain_openai import ChatOpenAI

        from services.profile_service import load_profile

        profile = load_profile()
        name = profile.get("full_name", "Candidate")
        date = application_date or "recently"
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.5)
        prompt = f"""Generate two brief professional follow-ups for a job applicant.
- Applicant: {name}
- Role: {job_title} at {company}
- Applied: {date}

1. LinkedIn message (2-3 sentences, max 200 chars): polite, reference the role, express continued interest.
2. Email subject + body (2-3 sentences): similar tone, professional.

Return as JSON: {{"linkedin_message": "...", "email_subject": "...", "email_body": "..."}}
"""
        r = llm.invoke([HumanMessage(content=prompt)])
        text = (r.content or "").strip()
        m = re.search(r"\{[\s\S]*\}", text)
        try:
            data = json.loads(m.group(0)) if m else {}
        except json.JSONDecodeError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        data.setdefault("linkedin_message", text[:200] if text else "")
        data.setdefault("email_subject", f"Following up - {job_title}")
        data.setdefault("email_body", text[:300] if text else "")
        return {"status": "ok", **data}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}
