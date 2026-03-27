"""submission_status labels for runner outcomes (log_application_from_result)."""

from dataclasses import dataclass

from services.application_tracker import _submission_status_for_run_result


@dataclass
class _FakeRun:
    status: str
    error: str = ""


def test_submission_applied_and_dry_run():
    assert _submission_status_for_run_result(_FakeRun("applied")) == "Applied"
    assert _submission_status_for_run_result(_FakeRun("dry_run")) == "Dry Run Complete"
    assert _submission_status_for_run_result(_FakeRun("manual_assist_ready")) == (
        "Manual Assist Ready"
    )


def test_submission_skipped_no_url_and_external():
    assert _submission_status_for_run_result(_FakeRun("skipped", "no_url")) == (
        "Skipped – No URL"
    )
    assert _submission_status_for_run_result(
        _FakeRun("skipped", "easy_apply_only: external ATS not processed")
    ) == ("Skipped – External ATS")


def test_submission_skipped_autonomy_gate():
    assert _submission_status_for_run_result(
        _FakeRun("skipped", "autonomy: pilot_submit_only")
    ) == ("Skipped – Autonomy Gate")


def test_submission_skipped_policy_variants():
    assert _submission_status_for_run_result(
        _FakeRun("skipped", "policy_blocked: fit_decision=reject")
    ) == ("Skipped – Low Fit")
    assert _submission_status_for_run_result(
        _FakeRun("skipped", "policy_blocked: ats_score=70<85")
    ) == ("Skipped – Low ATS")
    assert _submission_status_for_run_result(
        _FakeRun("skipped", "policy_blocked: unsupported_requirements")
    ) == ("Skipped – Unsupported Requirements")
    assert _submission_status_for_run_result(
        _FakeRun("skipped", "policy_blocked: apply_mode=skip")
    ) == ("Skipped – Policy")


def test_submission_shadow_statuses():
    assert _submission_status_for_run_result(_FakeRun("shadow_would_apply", "")) == (
        "Shadow – Would Apply"
    )
    assert _submission_status_for_run_result(
        _FakeRun("shadow_would_not_apply", "answerer_manual_review_required")
    ) == ("Shadow – Would Not Apply")


def test_submission_blocked_resume_verification():
    assert _submission_status_for_run_result(
        _FakeRun("blocked_resume_verification", "resume_verification_failed")
    ) == ("Blocked – Resume Verification")


def test_submission_failed_login_vs_form():
    assert _submission_status_for_run_result(
        _FakeRun("failed", "checkpoint in URL")
    ) == ("Failed – Login Challenge")
    assert _submission_status_for_run_result(_FakeRun("failed", "selector timeout")) == (
        "Failed – Form Unmapped"
    )
