"""
Batch fit + ATS scoring for job dicts (MCP ``batch_prioritize_jobs`` + REST parity).
"""

from __future__ import annotations

import json
from typing import Any, List, Union


def batch_prioritize_jobs_payload(
    jobs: Union[str, List[Any]],
    master_resume_text: str,
    max_scored: int = 20,
) -> dict[str, Any]:
    """
    Parse ``jobs`` from JSON string or list; score up to ``max_scored`` rows; sort by
    easy_apply_confirmed, fit_score, ats_score.
    """
    try:
        if isinstance(jobs, str):
            jobs = json.loads(jobs)
        if not isinstance(jobs, list) or not jobs:
            return {"status": "error", "message": "jobs must be a non-empty list"}

        cap = min(max(1, int(max_scored)), 200)
        from enhanced_ats_checker import EnhancedATSChecker
        from services.ats_service import check_fit_gate

        scored: list[dict[str, Any]] = []
        for j in jobs[:cap]:
            j = j if isinstance(j, dict) else {}
            jd = j.get("description", "") or j.get("job_details", "")
            if not jd or len(jd) < 100:
                scored.append(
                    {
                        **j,
                        "fit_score": 0,
                        "fit_decision": "manual_review",
                        "ats_score": 0,
                        "priority_note": "No JD",
                    }
                )
                continue
            state = {
                "base_resume_text": master_resume_text,
                "job_description": jd,
                "target_position": j.get("title", ""),
                "target_company": j.get("company", ""),
                "target_location": "USA",
            }
            fit = check_fit_gate(state)
            checker = EnhancedATSChecker()
            ats = checker.comprehensive_ats_check(
                resume_text=master_resume_text,
                job_description=jd,
                job_title=j.get("title", ""),
                company_name=j.get("company", ""),
                location="USA",
                target_truthful_score=100,
                master_resume_text=master_resume_text,
            )
            scored.append(
                {
                    "title": j.get("title"),
                    "company": j.get("company"),
                    "url": j.get("url"),
                    "easy_apply_confirmed": j.get("easy_apply_confirmed", False),
                    "fit_score": fit.get("job_fit_score", 0),
                    "fit_decision": fit.get("fit_decision", "manual_review"),
                    "ats_score": ats.get("ats_score", 0),
                }
            )
        scored.sort(
            key=lambda x: (
                -(x.get("easy_apply_confirmed") or False),
                -x.get("fit_score", 0),
                -x.get("ats_score", 0),
            )
        )
        return {"status": "ok", "prioritized": scored}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}
