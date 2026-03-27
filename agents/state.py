from typing import TypedDict, List, Optional, Literal

# ── Job-level states (first-class; must match DB schema and tracker) ──────────
JobState = Literal[
    "skip",           # Clear mismatch / hard blocker — no package, no automation
    "manual_review",  # Borderline fit — summary only, no browser actions
    "manual_assist",  # Good fit, human submits — full package, safe pre-fill only
    "safe_auto_apply",# High-confidence narrow class (LinkedIn Easy Apply + all gates pass)
    "blocked",        # Truth/policy prevents safe apply — no action allowed
]

# ── Per-answer/field states ───────────────────────────────────────────────────
AnswerState = Literal[
    "safe",     # Truthful, submit-safe — eligible for auto-fill
    "review",   # Truthful but requires human review before use
    "missing",  # Required info absent from truth inventory — triggers enrichment
    "blocked",  # Cannot be answered truthfully and safely
]

FitDecision = Literal["apply", "manual_review", "reject"]


class AgentState(TypedDict, total=False):
    # ── User / session scope ─────────────────────────────────────────────────
    user_id: str                    # Phase 3.1.2 — tracker / multi-user scope
    workspace_id: str               # Multi-tenant isolation key
    candidate_name: str
    target_position: str
    target_company: str
    target_location: str
    base_resume_text: str
    job_description: str

    # ── Job-level state machine ───────────────────────────────────────────────
    job_state: JobState             # Canonical state; persisted in DB + API responses
    previous_job_state: JobState    # Prior state (for audit / downgrade tracing)

    # ── Answer / field safety ─────────────────────────────────────────────────
    # Per-field answer states are stored as a dict keyed by field name.
    # Global summary flags are computed from the per-field dict.
    answer_states: dict             # {field_name: AnswerState}
    critical_fields: List[str]      # Fields that block auto-submit when not 'safe'

    # ── Truth and submission safety gates ────────────────────────────────────
    truth_safe: bool                # All critical answers grounded in truth inventory
    submit_safe: bool               # All critical answers appropriate for this job context
    safe_to_submit: bool            # truth_safe AND submit_safe AND all gates pass
                                    # Operator MUST treat False as a hard stop for auto-submit

    # ── JD Analyzer outputs ───────────────────────────────────────────────────
    is_eligible: bool
    eligibility_reason: str
    required_skills: List[str]
    preferred_skills: List[str]
    missing_skills: List[str]

    # ── ATS Scorer outputs ────────────────────────────────────────────────────
    initial_ats_score: int
    final_ats_score: int
    feedback: str
    ats_report_path: str

    # ── Job-fit gate (from master_resume_guard) ───────────────────────────────
    job_fit_score: Optional[int]
    fit_decision: FitDecision       # apply | manual_review | reject
    unsupported_requirements: List[str]
    truthful_missing_keywords: List[str]
    truth_safe_ats_ceiling: int     # Max ATS score achievable without fabrication
    truth_safe_ceiling_reason: str
    ceiling_limited_by: List[str]
    selected_address_label: str
    package_field_stats: dict

    # ── Resume Editor outputs ─────────────────────────────────────────────────
    tailored_resume_text: str
    humanized_resume_text: str
    generated_project_text: str

    # ── Cover Letter outputs ──────────────────────────────────────────────────
    cover_letter_text: str
    humanized_cover_letter_text: str

    # ── File Manager outputs ──────────────────────────────────────────────────
    final_pdf_path: str
    cover_letter_pdf_path: str

    # ── Application run telemetry ─────────────────────────────────────────────
    run_id: str                     # UUID for this application attempt
    shadow_mode: bool               # True → fill but never submit; log shadow intent
    dry_run: bool                   # True → fill forms, do not submit
    application_decision: dict      # Full MCP decision payload (v0 contract)
    submission_status: str          # Applied | Skipped | Shadow – Would Apply | etc.
    error: Optional[str]            # Last error string (prefixed 'autonomy:' for gate blocks)
