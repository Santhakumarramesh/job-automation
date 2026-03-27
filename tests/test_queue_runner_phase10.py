from __future__ import annotations

from pathlib import Path

import pytest

from services import apply_queue_service as qs
from services import resume_upload_binding as rub
from services import resume_version_store as rvs
from services.runner_queue_executor import run_approved_queue, RunnerConfig


@pytest.fixture
def queue_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setattr(qs, "DB_PATH", db_path)
    monkeypatch.setattr(rvs, "DB_PATH", db_path)
    return db_path


def _make_approved_item(tmp_path: Path) -> tuple[str, str]:
    item_id = qs.upsert_queue_item(
        job_url="https://www.linkedin.com/jobs/view/123",
        job_title="ML Engineer",
        company="ExampleCo",
        job_description="Python, ML",
        fit_data={"fit_decision": "apply", "overall_fit_score": 80},
    )
    pdf_path = tmp_path / "resume.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%EOF\n")
    version = rub.bind_approved_resume(item_id, approved_pdf_path=str(pdf_path))
    qs.approve_job(
        item_id,
        approval_metadata={
            "approved_resume_version_id": version.get("resume_version_id", ""),
            "approved_resume_path": version.get("approved_pdf_path", ""),
            "approved_at": version.get("approved_at", ""),
            "approved_by": version.get("approved_by", "user"),
        },
    )
    return item_id, str(pdf_path)


def test_runner_applied_updates_states(queue_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    item_id, _ = _make_approved_item(tmp_path)

    def _stub_apply(*args, **kwargs):
        return {
            "status": "ok",
            "applied": 1,
            "results": [{"status": "applied", "error": ""}],
        }

    import services.linkedin_browser_automation as lba
    monkeypatch.setattr(lba, "apply_to_jobs_payload", _stub_apply)

    out = run_approved_queue(RunnerConfig(dry_run=False, max_jobs=10, rate_limit_seconds=0))
    assert out["processed"] == 1

    item = qs.get_item_by_id(item_id)
    assert item["job_state"] == qs.JobQueueState.APPLIED
    assert item.get("runner_state") == "submitted"


def test_runner_stops_on_manual_assist(queue_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    item_id, _ = _make_approved_item(tmp_path)

    def _stub_apply(*args, **kwargs):
        return {
            "status": "ok",
            "applied": 0,
            "results": [{"status": "manual_assist_ready", "error": "answerer_manual_review_required"}],
        }

    import services.linkedin_browser_automation as lba
    monkeypatch.setattr(lba, "apply_to_jobs_payload", _stub_apply)

    out = run_approved_queue(RunnerConfig(dry_run=False, max_jobs=10, rate_limit_seconds=0))
    assert out["processed"] == 1

    item = qs.get_item_by_id(item_id)
    assert item["job_state"] == qs.JobQueueState.REVIEW_RESUME
    assert item.get("runner_state") == "stopped_review_required"


def test_runner_blocks_resume_verification_failure(queue_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    item_id, _ = _make_approved_item(tmp_path)

    def _stub_apply(*args, **kwargs):
        return {
            "status": "ok",
            "applied": 0,
            "results": [{"status": "blocked_resume_verification", "error": "resume_verification_failed"}],
        }

    import services.linkedin_browser_automation as lba
    monkeypatch.setattr(lba, "apply_to_jobs_payload", _stub_apply)

    out = run_approved_queue(RunnerConfig(dry_run=False, max_jobs=10, rate_limit_seconds=0))
    assert out["processed"] == 1

    item = qs.get_item_by_id(item_id)
    assert item["job_state"] == qs.JobQueueState.BLOCKED
    assert item.get("runner_state") == "failed"


def test_runner_blocks_missing_resume(queue_db: Path):
    item_id = qs.upsert_queue_item(
        job_url="https://www.linkedin.com/jobs/view/456",
        job_title="ML Engineer",
        company="ExampleCo",
        job_description="Python, ML",
        fit_data={"fit_decision": "apply", "overall_fit_score": 80},
    )
    qs.approve_job(item_id, approval_metadata={})

    out = run_approved_queue(RunnerConfig(dry_run=False, max_jobs=10, rate_limit_seconds=0))
    assert out["processed"] == 1

    item = qs.get_item_by_id(item_id)
    assert item["job_state"] == qs.JobQueueState.BLOCKED
    assert item.get("runner_state") == "failed"
