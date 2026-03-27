from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.application_runner import RunResult
from services import application_tracker as at
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


def test_tracker_logs_lifecycle_fields():
    job = {
        "job_id": "queue-1",
        "fit_decision": "apply",
        "fit_state": "apply",
        "package_state": "approved",
        "approval_state": "approved",
        "queue_state": "approved_for_apply",
        "runner_state": "submitted",
        "final_state": "applied",
        "ats_score": 90,
        "easy_apply_confirmed": True,
        "description": "JD text",
        "apply_url": "https://www.linkedin.com/jobs/view/123",
    }
    rr = RunResult(
        status="applied",
        company="ExampleCo",
        position="ML Engineer",
        job_url="https://www.linkedin.com/jobs/view/123",
    )
    at.log_runner_result_to_tracker(job, rr, resume_path="/tmp/resume.pdf")
    df = at.load_applications()
    assert len(df) == 1
    row = df.iloc[0]
    assert row["fit_state"] == "apply"
    assert row["package_state"] == "approved"
    assert row["approval_state"] == "approved"
    assert row["queue_state"] == "approved_for_apply"
    assert row["runner_state"] == "submitted"
    assert row["final_state"] == "applied"


def _make_approved_item(tmp_path: Path, suffix: str) -> str:
    item_id = qs.upsert_queue_item(
        job_url=f"https://www.linkedin.com/jobs/view/999{suffix}",
        job_title=f"ML Engineer {suffix}",
        company="ExampleCo",
        job_description="Python, ML",
        fit_data={"fit_decision": "apply", "overall_fit_score": 80},
    )
    pdf_path = tmp_path / f"{item_id}.pdf"
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
    return item_id


def test_audit_events_for_runner(queue_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setenv("AUDIT_LOG_PATH", str(audit_path))

    _make_approved_item(tmp_path, "A")
    _make_approved_item(tmp_path, "B")

    call = {"n": 0}

    def _stub_apply(*args, **kwargs):
        call["n"] += 1
        if call["n"] == 1:
            return {"status": "ok", "results": [{"status": "applied", "error": ""}]}
        return {"status": "ok", "results": [{"status": "manual_assist_ready", "error": "needs_review"}]}

    import services.linkedin_browser_automation as lba
    monkeypatch.setattr(lba, "apply_to_jobs_payload", _stub_apply)

    run_approved_queue(RunnerConfig(dry_run=False, max_jobs=5, rate_limit_seconds=0))

    actions = [json.loads(line)["action"] for line in audit_path.read_text().splitlines()]
    assert "runner_started" in actions
    assert "application_submitted" in actions
    assert "runner_stopped_review_required" in actions
