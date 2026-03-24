"""build_answerer_preview_for_export — Streamlit export alignment with policy."""

from agents.application_answerer import build_answerer_preview_for_export


def test_preview_empty_profile_flags_manual_review():
    review, pending = build_answerer_preview_for_export({}, {"title": "Eng", "company": "Co", "description": "JD"})
    assert pending is True
    assert any(v.get("manual_review_required") for v in review.values())


def test_preview_complete_profile_reduces_flags():
    profile = {
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
    review, pending = build_answerer_preview_for_export(
        profile, {"title": "MLE", "company": "Acme", "description": "Python ML role"}
    )
    assert pending is False
    assert not any(v.get("manual_review_required") for v in review.values())


def test_enrich_job_dict_auto_lane_when_profile_and_preview_clean():
    from services.policy_service import REASON_AUTO_OK, enrich_job_dict_for_policy_export

    profile = {
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
    out = enrich_job_dict_for_policy_export(
        job, profile=profile, master_resume_text="resume text " * 20, use_llm_preview=False
    )
    assert out["apply_mode"] == "auto_easy_apply"
    assert out["policy_reason"] == REASON_AUTO_OK
    assert out.get("answerer_manual_review_required") is False


def test_policy_from_exported_job_sees_preview():
    from services.policy_service import REASON_MANUAL_ANSWERER_REVIEW, policy_from_exported_job

    job = {
        "url": "https://linkedin.com/jobs/view/1",
        "easy_apply_confirmed": True,
        "fit_decision": "apply",
        "ats_score": 90,
        "unsupported_requirements": [],
        "answerer_manual_review_required": True,
    }
    mode, reason = policy_from_exported_job(job)
    assert mode == "manual_assist"
    assert reason == REASON_MANUAL_ANSWERER_REVIEW
