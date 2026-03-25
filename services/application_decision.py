"""
Unified application decision payload (contract v0.1).

Maps existing policy + canonical answerer preview into job_state, per-field
answer_state, truth_safe / submit_safe, and safe_to_submit.

See docs/MCP_APPLICATION_DECISION_CONTRACT.md.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from agents.application_answerer import (
    CANONICAL_SCREENING_FIELD_KEYS,
    REASON_GENERIC_LLM,
    REASON_PLACEHOLDER_MANUAL,
)
from services.policy_service import enrich_job_dict_for_policy_export


def _map_apply_mode_to_job_state(apply_mode: str) -> str:
    if apply_mode == "auto_easy_apply":
        return "safe_auto_apply"
    if apply_mode == "skip":
        return "skip"
    return "manual_assist"


def _answer_state_from_meta(manual: bool, answer: str, reason_codes: list[str]) -> str:
    if not manual:
        return "safe"
    codes = set(reason_codes or [])
    text = str(answer or "").strip()
    placeholderish = not text or text.lower().startswith("please review")
    if placeholderish or "empty_no_profile_data" in codes:
        return "missing"
    return "review"


def _truth_safe(reason_codes: list[str]) -> bool:
    codes = set(reason_codes or [])
    if REASON_GENERIC_LLM in codes:
        return False
    if REASON_PLACEHOLDER_MANUAL in codes:
        return False
    return True


def _submit_safe(answer_state: str, truth_ok: bool) -> bool:
    return answer_state == "safe" and truth_ok


def build_application_decision(
    job: Dict[str, Any],
    *,
    profile: Optional[dict] = None,
    master_resume_text: str = "",
    use_llm_preview: bool = False,
    blocked_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build v0.1 decision dict for one job.

    Uses ``enrich_job_dict_for_policy_export`` so ``apply_mode`` / ``policy_reason``
    match Streamlit export and MCP policy.

    ``blocked_reason``: optional runner/browser hard stop (e.g. checkpoint);
    forces ``job_state=blocked`` and ``safe_to_submit=false``.
    """
    enriched = enrich_job_dict_for_policy_export(
        dict(job or {}),
        profile=profile,
        master_resume_text=master_resume_text or "",
        use_llm_preview=use_llm_preview,
    )
    apply_mode = str(enriched.get("apply_mode") or "manual_assist")
    policy_reason = str(enriched.get("policy_reason") or "")
    fit_decision = str(enriched.get("fit_decision") or "")

    reasons: list[str] = []
    if blocked_reason:
        reasons.append(str(blocked_reason))
    if policy_reason:
        reasons.append(policy_reason)

    if blocked_reason:
        job_state = "blocked"
    else:
        job_state = _map_apply_mode_to_job_state(apply_mode)

    review = enriched.get("answerer_review") or {}
    if not isinstance(review, dict):
        review = {}

    answers_out: Dict[str, Any] = {}
    for key in CANONICAL_SCREENING_FIELD_KEYS:
        meta = review.get(key)
        if not isinstance(meta, dict):
            meta = {}
        manual = bool(meta.get("manual_review_required"))
        rc = meta.get("reason_codes") or []
        if not isinstance(rc, list):
            rc = [str(x) for x in rc] if rc else []
        else:
            rc = [str(x) for x in rc]
        text = str(meta.get("answer") or "")
        ast = _answer_state_from_meta(manual, text, rc)
        ts = _truth_safe(rc)
        ss = _submit_safe(ast, ts)
        answers_out[key] = {
            "answer_state": ast,
            "truth_safe": ts,
            "submit_safe": ss,
            "text": text[:500],
            "reason_codes": rc,
        }

    critical_unsatisfied = [
        k
        for k in CANONICAL_SCREENING_FIELD_KEYS
        if not answers_out[k]["submit_safe"] or answers_out[k]["answer_state"] != "safe"
    ]

    safe_to_submit = (
        job_state == "safe_auto_apply"
        and not blocked_reason
        and len(critical_unsatisfied) == 0
    )

    return {
        "schema_version": "0.1",
        "job_state": job_state,
        "safe_to_submit": safe_to_submit,
        "apply_mode_legacy": apply_mode,
        "policy_reason": policy_reason,
        "fit_decision": fit_decision,
        "reasons": reasons,
        "answers": answers_out,
        "critical_unsatisfied": critical_unsatisfied,
    }


def application_decision_json_for_tracker_job(
    job: Dict[str, Any],
    *,
    profile: Optional[dict] = None,
    master_resume_text: str = "",
    blocked_reason: Optional[str] = None,
    max_len: int = 31000,
) -> str:
    """Serialize v0.1 decision JSON for tracker ``application_decision`` column."""
    d = build_application_decision(
        dict(job or {}),
        profile=profile,
        master_resume_text=master_resume_text or "",
        blocked_reason=blocked_reason,
    )
    return json.dumps(d, separators=(",", ":"))[:max_len]
