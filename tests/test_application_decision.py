"""build_application_decision — contract v0.1 payload."""

import json

from services.application_decision import (
    application_decision_json_for_tracker_job,
    build_application_decision,
    extract_job_state_from_decision_json,
    normalize_job_state_for_tracker,
    safe_auto_apply_precondition_checklist,
)


def _complete_profile():
    return {
        "full_name": "A",
        "email": "a@b.co",
        "phone": "1",
        "linkedin_url": "https://linkedin.com/in/x",
        "github_url": "https://github.com/x",
        "portfolio_url": "https://x.dev",
        "work_authorization_note": "US citizen",
        "notice_period": "2 weeks",
        "salary_expectation_rule": "Negotiable",
        "relocation_preference": "Remote",
        "mailing_address": {
            "street_line1": "1 Main",
            "city": "SF",
            "state_region": "CA",
            "postal_code": "94102",
            "country": "US",
        },
        "short_answers": {
            "sponsorship": "No sponsorship",
            "why_this_role": "I enjoy building ML systems.",
            "why_this_company": "Mission aligned.",
            "availability": "Immediate",
            "years_python": "5+",
            "years_ml": "3+",
        },
    }


def test_decision_skip_low_fit():
    out = build_application_decision(
        {
            "url": "https://linkedin.com/jobs/view/1",
            "easy_apply_confirmed": True,
            "fit_decision": "reject",
        },
        profile=_complete_profile(),
    )
    assert out["job_state"] == "skip"
    assert out["apply_mode_legacy"] == "skip"
    assert out["safe_to_submit"] is False


def test_decision_manual_assist_external_apply():
    out = build_application_decision(
        {
            "url": "https://linkedin.com/jobs/view/1",
            "apply_url": "https://boards.greenhouse.io/acme/jobs/9",
            "easy_apply_confirmed": True,
            "fit_decision": "apply",
            "ats_score": 90,
            "unsupported_requirements": [],
        },
        profile=_complete_profile(),
    )
    assert out["job_state"] == "manual_assist"
    assert out["safe_to_submit"] is False


def test_decision_safe_auto_apply_when_policy_and_answers_clean():
    job = {
        "url": "https://linkedin.com/jobs/view/9",
        "easy_apply_confirmed": True,
        "title": "MLE",
        "company": "Acme",
        "description": "Python ML",
        "fit_decision": "apply",
        "ats_score": 92,
        "unsupported_requirements": [],
    }
    out = build_application_decision(
        job,
        profile=_complete_profile(),
        master_resume_text="resume text " * 20,
    )
    assert out["job_state"] == "safe_auto_apply"
    assert out["apply_mode_legacy"] == "auto_easy_apply"
    assert out["safe_to_submit"] is True
    assert out["critical_unsatisfied"] == []
    chk = safe_auto_apply_precondition_checklist(
        out,
        easy_apply_confirmed=True,
    )
    assert all(r["satisfied"] for r in chk)
    assert len(chk) == 5


def test_safe_auto_apply_precondition_checklist_skip_job():
    out = build_application_decision(
        {
            "url": "https://linkedin.com/jobs/view/1",
            "easy_apply_confirmed": True,
            "fit_decision": "reject",
        },
        profile=_complete_profile(),
    )
    chk = safe_auto_apply_precondition_checklist(out, easy_apply_confirmed=True)
    assert chk[0]["satisfied"] is False
    assert chk[2]["satisfied"] is False
    assert any(r["satisfied"] is False for r in chk)


def test_decision_blocked_reason_overrides():
    job = {
        "url": "https://linkedin.com/jobs/view/9",
        "easy_apply_confirmed": True,
        "fit_decision": "apply",
        "ats_score": 92,
        "unsupported_requirements": [],
    }
    out = build_application_decision(
        job,
        profile=_complete_profile(),
        blocked_reason="linkedin_checkpoint",
    )
    assert out["job_state"] == "blocked"
    assert out["safe_to_submit"] is False
    assert "linkedin_checkpoint" in out["reasons"]


def test_application_decision_json_for_tracker_job_roundtrip():
    raw = application_decision_json_for_tracker_job(
        {
            "url": "https://linkedin.com/jobs/view/1",
            "easy_apply_confirmed": True,
            "fit_decision": "reject",
        },
        profile=_complete_profile(),
    )
    d = json.loads(raw)
    assert d["schema_version"] == "0.1"
    assert d["job_state"] == "skip"
    assert "answers" in d
    assert extract_job_state_from_decision_json(raw) == "skip"
    assert extract_job_state_from_decision_json("") == ""
    assert extract_job_state_from_decision_json("not json") == ""


def test_extract_job_state_normalizes_case_and_rejects_unknown():
    assert normalize_job_state_for_tracker("Manual_Assist") == "manual_assist"
    assert normalize_job_state_for_tracker("not-a-real-state") == ""
    raw = json.dumps({"schema_version": "0.1", "job_state": "totally_invalid"})
    assert extract_job_state_from_decision_json(raw) == ""
