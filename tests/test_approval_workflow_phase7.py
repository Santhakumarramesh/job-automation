from __future__ import annotations

from pathlib import Path

import pytest

from services import apply_queue_service as qs
from services import approval_service


@pytest.fixture
def queue_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setattr(qs, "DB_PATH", db_path)
    yield db_path


def _fit_payload():
    return {
        "role_family": "ai_ml_engineer",
        "seniority_band": "mid",
        "role_match_score": 90,
        "experience_match_score": 80,
        "seniority_match_score": 75,
        "overall_fit_score": 70,
        "fit_decision": "apply",
        "fit_reasons": ["Strong fit"],
        "unsupported_requirements": [],
        "hard_blockers": [],
        "requirement_evidence_map": [],
    }


def test_approval_records_metadata(queue_db: Path, monkeypatch: pytest.MonkeyPatch):
    item_id = qs.upsert_queue_item(
        job_url="https://example.com/job/1",
        job_title="ML Engineer",
        company="ExampleCo",
        job_description="Python, ML",
        fit_data=_fit_payload(),
    )
    qs.attach_package(
        item_id,
        {
            "resume_version_id": "res1",
            "package_status": qs.PackageState.OPTIMIZED_TRUTH_SAFE,
            "initial_ats_score": 70,
            "final_ats_score": 82,
            "truth_safe_ats_ceiling": 85,
            "resume_path": "/tmp/resume.pdf",
        },
    )

    monkeypatch.setattr(approval_service, "load_package", lambda _rid: {"rendered_pdf_path": "/tmp/one_page.pdf"})
    result = approval_service.approve_job_with_metadata(item_id, approved_by="tester")
    assert result["status"] == "ok"

    item = qs.get_item_by_id(item_id)
    assert item["job_state"] == qs.JobQueueState.APPROVED_FOR_APPLY
    assert item["approval_status"] == "approved"
    assert item.get("approved_resume_version_id") == "res1"


def test_hold_reject_send_back(queue_db: Path):
    item_id = qs.upsert_queue_item(
        job_url="https://example.com/job/2",
        job_title="ML Engineer",
        company="ExampleCo",
        job_description="Python, ML",
        fit_data=_fit_payload(),
    )
    approval_service.hold_job_for_review(item_id)
    item = qs.get_item_by_id(item_id)
    assert item["approval_status"] == "hold"

    approval_service.send_back_for_regeneration(item_id)
    item = qs.get_item_by_id(item_id)
    assert item["job_state"] == qs.JobQueueState.REVIEW_RESUME

    approval_service.reject_job_for_apply(item_id, notes="Not a fit")
    item = qs.get_item_by_id(item_id)
    assert item["job_state"] == qs.JobQueueState.SKIP
