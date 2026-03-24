"""
Critical flow tests: policy, profile, fit gate, tracker, audit, startup checks.
"""

import os
import tempfile
from pathlib import Path

import pytest


class TestPolicy:
    """Policy service: decide_apply_mode."""

    def test_skip_on_reject_fit(self):
        from services.policy_service import decide_apply_mode, decide_apply_mode_with_reason, REASON_SKIP_FIT
        assert decide_apply_mode({}, fit_decision="reject") == "skip"
        assert decide_apply_mode({}, fit_decision="Reject") == "skip"
        m, r = decide_apply_mode_with_reason({}, fit_decision="reject")
        assert m == "skip" and r == REASON_SKIP_FIT

    def test_legacy_review_fit_normalized_and_skips(self):
        from services.policy_service import (
            REASON_SKIP_FIT,
            decide_apply_mode_with_reason,
            normalize_fit_decision_label,
        )

        assert normalize_fit_decision_label("review") == "manual_review"
        assert normalize_fit_decision_label("Review") == "manual_review"
        m, r = decide_apply_mode_with_reason(
            {},
            fit_decision="review",
            ats_score=95,
            unsupported_requirements=[],
            profile_ready=True,
        )
        assert m == "skip" and r == REASON_SKIP_FIT

    def test_skip_on_unsupported_requirements(self):
        from services.policy_service import decide_apply_mode
        assert decide_apply_mode({}, unsupported_requirements=["secret clearance"]) == "skip"

    def test_skip_on_low_ats(self):
        from services.policy_service import decide_apply_mode, FIT_THRESHOLD_AUTO_APPLY
        assert decide_apply_mode({}, ats_score=FIT_THRESHOLD_AUTO_APPLY - 1) == "skip"
        assert decide_apply_mode({}, ats_score=50) == "skip"

    def test_manual_assist_non_linkedin(self):
        from services.policy_service import decide_apply_mode
        job = {"url": "https://indeed.com/job/123", "easy_apply_confirmed": True}
        assert decide_apply_mode(job) == "manual_assist"

    def test_manual_assist_linkedin_company_not_jobs_path(self):
        from services.policy_service import decide_apply_mode, decide_apply_mode_with_reason
        job = {
            "url": "https://www.linkedin.com/company/acme",
            "easy_apply_confirmed": True,
        }
        assert decide_apply_mode(job) == "manual_assist"
        m, r = decide_apply_mode_with_reason(
            job, fit_decision="apply", ats_score=95, unsupported_requirements=[], profile_ready=True
        )
        assert m == "manual_assist"

    def test_manual_assist_external_apply_url_from_linkedin_listing(self):
        from services.policy_service import (
            decide_apply_mode_with_reason,
            REASON_MANUAL_EXTERNAL_APPLY_TARGET,
        )

        job = {
            "url": "https://linkedin.com/jobs/view/123",
            "apply_url": "https://boards.greenhouse.io/acme/jobs/999",
            "easy_apply_confirmed": True,
        }
        m, r = decide_apply_mode_with_reason(
            job, fit_decision="apply", ats_score=95, unsupported_requirements=[], profile_ready=True
        )
        assert m == "manual_assist"
        assert r == REASON_MANUAL_EXTERNAL_APPLY_TARGET

    def test_auto_easy_apply_linkedin_confirmed(self):
        from services.policy_service import decide_apply_mode
        job = {
            "url": "https://linkedin.com/jobs/view/123",
            "easy_apply_confirmed": True,
        }
        assert decide_apply_mode(job) == "auto_easy_apply"

    def test_profile_incomplete_downgrades_auto(self):
        from services.policy_service import (
            decide_apply_mode_with_reason,
            REASON_MANUAL_PROFILE_INCOMPLETE,
            REASON_AUTO_OK,
        )
        job = {"url": "https://linkedin.com/jobs/view/999", "easy_apply_confirmed": True}
        m, r = decide_apply_mode_with_reason(
            job, fit_decision="apply", ats_score=95, unsupported_requirements=[], profile_ready=False
        )
        assert m == "manual_assist"
        assert r == REASON_MANUAL_PROFILE_INCOMPLETE
        m2, r2 = decide_apply_mode_with_reason(
            job, fit_decision="apply", ats_score=95, unsupported_requirements=[], profile_ready=True
        )
        assert m2 == "auto_easy_apply" and r2 == REASON_AUTO_OK

    def test_profile_gate_skipped_when_none(self):
        """profile_ready=None does not block auto (discovery / legacy callers)."""
        from services.policy_service import decide_apply_mode_with_reason, REASON_AUTO_OK
        job = {"url": "https://linkedin.com/jobs/view/1", "easy_apply_confirmed": True}
        m, r = decide_apply_mode_with_reason(job, profile_ready=None)
        assert m == "auto_easy_apply" and r == REASON_AUTO_OK

    def test_answerer_manual_review_required_downgrades_auto(self):
        from services.policy_service import (
            decide_apply_mode_with_reason,
            REASON_AUTO_OK,
            REASON_MANUAL_ANSWERER_REVIEW,
        )

        job = {
            "url": "https://linkedin.com/jobs/view/42",
            "easy_apply_confirmed": True,
            "answerer_manual_review_required": True,
        }
        m, r = decide_apply_mode_with_reason(
            job, fit_decision="apply", ats_score=95, unsupported_requirements=[], profile_ready=True
        )
        assert m == "manual_assist" and r == REASON_MANUAL_ANSWERER_REVIEW
        m2, r2 = decide_apply_mode_with_reason(
            {**job, "answerer_manual_review_required": False},
            fit_decision="apply",
            ats_score=95,
            unsupported_requirements=[],
            profile_ready=True,
        )
        assert m2 == "auto_easy_apply" and r2 == REASON_AUTO_OK

    def test_answerer_review_dict_downgrades_auto(self):
        from services.policy_service import decide_apply_mode_with_reason, REASON_MANUAL_ANSWERER_REVIEW

        job = {
            "url": "https://linkedin.com/jobs/view/43",
            "easy_apply_confirmed": True,
            "answerer_review": {"salary": {"manual_review_required": True, "reason_codes": ["ambiguous"]}},
        }
        m, r = decide_apply_mode_with_reason(
            job, fit_decision="apply", ats_score=90, unsupported_requirements=[], profile_ready=True
        )
        assert m == "manual_assist" and r == REASON_MANUAL_ANSWERER_REVIEW


class TestProfile:
    """Master resume parsing: parse_master_resume."""

    def test_parse_short_returns_empty(self):
        from agents.master_resume_guard import parse_master_resume
        p = parse_master_resume("short")
        assert p.raw_text_lower == ""
        assert len(p.skills) == 0

    def test_parse_extracts_skills(self):
        from agents.master_resume_guard import parse_master_resume
        text = "Python SQL AWS TensorFlow. Machine learning engineer. " * 15  # >100 chars
        p = parse_master_resume(text)
        assert "python" in p.raw_text_lower
        assert "python" in {s.lower() for s in (p.skills | p.tools)}


class TestFitGate:
    """Fit gate: is_job_fit."""

    def test_fit_apply_when_strong_match(self):
        from agents.master_resume_guard import parse_master_resume, is_job_fit
        text = "Python TensorFlow AWS Machine Learning. " * 20
        profile = parse_master_resume(text)
        jd = "We need Python and AWS experience. Machine learning preferred."
        result = is_job_fit(profile, jd, ats_score=90)
        assert result.decision in ("apply", "manual_review")
        assert result.score >= 0

    def test_fit_reject_on_unsupported(self):
        from agents.master_resume_guard import parse_master_resume, is_job_fit
        text = "Python developer. " * 15
        profile = parse_master_resume(text)
        jd = "Must have Top Secret clearance and 10 years COBOL."
        result = is_job_fit(profile, jd, ats_score=50)
        assert result.unsupported_requirements or result.decision in ("reject", "manual_review")


class TestMasterResumeTruth:
    """load_master_resume_text + truth inventory helpers."""

    def test_load_inline_and_inventory(self):
        from agents.master_resume_guard import (
            load_master_resume_text,
            parse_master_resume,
            truth_inventory_from_profile,
        )

        long = "Python developer with AWS and machine learning experience. " * 12
        text, src = load_master_resume_text(inline_text=long)
        assert src == "inline_text" and len(text) >= 100
        inv = truth_inventory_from_profile(parse_master_resume(text))
        assert isinstance(inv["skills"], list)
        assert any(str(s).lower() == "python" for s in inv["skills"])

    def test_load_from_text_file(self):
        from agents.master_resume_guard import (
            load_master_resume_text,
            parse_master_resume,
            truth_inventory_from_profile,
        )

        root = Path(__file__).resolve().parent.parent
        p = root / "_tmp_truth_cv_test.txt"
        body = "Python SQL AWS TensorFlow data science professional. " * 15
        try:
            p.write_text(body, encoding="utf-8")
            text, src = load_master_resume_text(path="_tmp_truth_cv_test.txt")
            assert len(text) >= 100
            assert "_tmp_truth_cv_test.txt" in src or str(p) == src
            inv = truth_inventory_from_profile(parse_master_resume(text))
            assert len(inv["skills"]) >= 1
        finally:
            p.unlink(missing_ok=True)

    def test_resolve_project_relative_rejects_escape(self):
        from agents.master_resume_guard import resolve_project_relative_resume_path

        with pytest.raises(ValueError):
            resolve_project_relative_resume_path("../.env")


class TestTracker:
    """Application tracker: log and load."""

    def test_tracker_csv_mode(self):
        os.environ["TRACKER_USE_DB"] = "0"
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / "job_applications.csv"
            # Patch APPLICATION_FILE so we don't touch repo root
            import services.application_tracker as at
            orig = at.APPLICATION_FILE
            at.APPLICATION_FILE = csv_path
            try:
                at.initialize_tracker()
                state = {
                    "job_id": "test-123",
                    "job_url": "https://example.com/job",
                    "apply_url": "https://example.com/apply",
                    "target_company": "TestCo",
                    "target_position": "Engineer",
                    "user_id": "test-user",
                }
                at.log_application(state)
                assert csv_path.exists()
                content = csv_path.read_text()
                assert "TestCo" in content or "test-123" in content
            finally:
                at.APPLICATION_FILE = orig

    def test_tracker_db_log_and_load(self):
        os.environ["TRACKER_USE_DB"] = "1"
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "test_apps.db"
            os.environ["DATABASE_URL"] = f"sqlite:///{db}"
            try:
                from services.tracker_db import initialize_tracker_db, log_application_db, load_applications_db
                initialize_tracker_db()
                row = {
                    "source": "test",
                    "job_id": "j-1",
                    "company": "TestCo",
                    "position": "Engineer",
                    "user_id": "db-user",
                }
                rid = log_application_db(row)
                assert rid
                df = load_applications_db()
                assert len(df) >= 1
                assert (df["job_id"] == "j-1").any()
            finally:
                os.environ.pop("DATABASE_URL", None)
                os.environ.pop("TRACKER_DB_PATH", None)


class TestUserBinding:
    """Phase 3.1.2: tracker rows scoped by user_id."""

    def test_load_applications_filters_by_user_id(self):
        os.environ["TRACKER_USE_DB"] = "0"
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / "job_applications.csv"
            import services.application_tracker as at
            orig = at.APPLICATION_FILE
            at.APPLICATION_FILE = csv_path
            try:
                at.initialize_tracker()
                at.log_application(
                    {
                        "target_company": "A",
                        "target_position": "X",
                        "job_id": "1",
                        "user_id": "alice",
                    }
                )
                at.log_application(
                    {
                        "target_company": "B",
                        "target_position": "Y",
                        "job_id": "2",
                        "user_id": "bob",
                    }
                )
                all_df = at.load_applications(for_user_id=None)
                assert len(all_df) >= 2
                alice_df = at.load_applications(for_user_id="alice")
                assert len(alice_df) == 1
                assert alice_df.iloc[0]["company"] == "A"
                row = at.get_application_row_by_job_id("1", for_user_id="alice")
                assert row is not None
                assert row["company"] == "A"
                assert at.get_application_row_by_job_id("2", for_user_id="alice") is None
            finally:
                at.APPLICATION_FILE = orig

    def test_get_application_row_by_job_id_demo_scope(self):
        """for_user_id=None finds job across users."""
        os.environ["TRACKER_USE_DB"] = "0"
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / "job_applications.csv"
            import services.application_tracker as at
            orig = at.APPLICATION_FILE
            at.APPLICATION_FILE = csv_path
            try:
                at.initialize_tracker()
                at.log_application(
                    {
                        "target_company": "Co",
                        "target_position": "Dev",
                        "job_id": "jid-global",
                        "user_id": "someone",
                    }
                )
                row = at.get_application_row_by_job_id("jid-global", for_user_id=None)
                assert row is not None
                assert row["job_id"] == "jid-global"
            finally:
                at.APPLICATION_FILE = orig

    def test_artifact_metadata_from_row(self):
        from services.artifact_metadata import build_artifact_metadata
        import json

        row = {
            "resume_path": "/r.pdf",
            "cover_letter_path": "/c.pdf",
            "screenshots_path": json.dumps(["/a.png"]),
            "qa_audit": json.dumps({"q1": "a1"}),
            "artifacts_manifest": json.dumps({"s3_resume": "s3://b/k"}),
        }
        meta = build_artifact_metadata(row)
        assert meta["resume_path"] == "/r.pdf"
        assert meta["screenshots"] == ["/a.png"]
        assert meta["qa_audit"] == {"q1": "a1"}
        assert meta["artifacts_manifest"] == {"s3_resume": "s3://b/k"}


def _has_observability():
    import importlib.util
    return importlib.util.find_spec("services.observability") is not None


@pytest.mark.skipif(not _has_observability(), reason="services.observability not installed")
class TestAuditLog:
    """Observability: audit_log."""

    def test_audit_log_writes_line(self):
        with tempfile.TemporaryDirectory() as td:
            log_path = Path(td) / "audit.jsonl"
            prev = os.environ.get("AUDIT_LOG_PATH")
            os.environ["AUDIT_LOG_PATH"] = str(log_path)
            try:
                import services.observability as obs
                import importlib
                importlib.reload(obs)
                obs.audit_log("test_action", job_id="j1", company="Co", position="Dev")
                assert obs.AUDIT_LOG_PATH.exists()
                lines = obs.AUDIT_LOG_PATH.read_text().strip().split("\n")
                assert len(lines) >= 1
                assert "test_action" in lines[-1]
                assert "j1" in lines[-1]
            finally:
                if prev is not None:
                    os.environ["AUDIT_LOG_PATH"] = prev
                else:
                    os.environ.pop("AUDIT_LOG_PATH", None)


def _has_startup_checks():
    import importlib.util
    return importlib.util.find_spec("services.startup_checks") is not None


@pytest.mark.skipif(not _has_startup_checks(), reason="services.startup_checks not installed")
class TestStartupChecks:
    """Startup validation: run_startup_checks."""

    def test_startup_checks_run(self):
        import os
        from unittest.mock import patch

        from services.startup_checks import run_startup_checks

        # Avoid sys.exit if CI has APP_ENV=production without API keys
        with patch.dict(
            os.environ,
            {"APP_ENV": "development", "STRICT_STARTUP": "0"},
            clear=False,
        ):
            run_startup_checks("app")
            run_startup_checks("streamlit")
        # Should not raise; may print warnings
