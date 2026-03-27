from __future__ import annotations

from pathlib import Path

import pytest

from services import apply_queue_service as qs


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


def test_queue_item_creation_sets_review_fit(queue_db: Path):
    item_id = qs.upsert_queue_item(
        job_url="https://example.com/job/1",
        job_title="ML Engineer",
        company="ExampleCo",
        job_description="Python, ML",
        fit_data=_fit_payload(),
        ats_score=80,
        truth_safe_ceiling=85,
    )
    item = qs.get_item_by_id(item_id)
    assert item["job_state"] == qs.JobQueueState.REVIEW_FIT
    assert item["package_status"] == qs.PackageState.NOT_GENERATED
    assert item["recommended_action"] == "generate_package"


def test_attach_package_moves_ready_for_approval(queue_db: Path):
    item_id = qs.upsert_queue_item(
        job_url="https://example.com/job/2",
        job_title="ML Engineer",
        company="ExampleCo",
        job_description="Python, ML",
        fit_data=_fit_payload(),
        ats_score=80,
        truth_safe_ceiling=85,
    )
    qs.attach_package(
        item_id,
        {
            "resume_version_id": "res1",
            "package_status": qs.PackageState.OPTIMIZED_TRUTH_SAFE,
            "initial_ats_score": 70,
            "final_ats_score": 82,
            "truth_safe_ats_ceiling": 85,
            "covered_keywords": ["python"],
            "truthful_missing_keywords": [],
            "optimization_summary": "OK",
            "resume_path": "/tmp/resume.pdf",
        },
    )
    item = qs.get_item_by_id(item_id)
    assert item["package_status"] == qs.PackageState.OPTIMIZED_TRUTH_SAFE
    assert item["job_state"] == qs.JobQueueState.READY_FOR_APPROVAL


def test_hard_blocked_job_stays_skip(queue_db: Path):
    fit = _fit_payload()
    fit["hard_blockers"] = ["Requires clearance"]
    item_id = qs.upsert_queue_item(
        job_url="https://example.com/job/3",
        job_title="ML Engineer",
        company="ExampleCo",
        job_description="Python, ML",
        fit_data=fit,
    )
    qs.attach_package(
        item_id,
        {
            "resume_version_id": "res2",
            "package_status": qs.PackageState.GENERATED,
            "initial_ats_score": 60,
            "final_ats_score": 60,
            "truth_safe_ats_ceiling": 60,
        },
    )
    item = qs.get_item_by_id(item_id)
    assert item["job_state"] == qs.JobQueueState.SKIP


def test_queue_row_summary_fields(queue_db: Path):
    item_id = qs.upsert_queue_item(
        job_url="https://example.com/job/4",
        job_title="ML Engineer",
        company="ExampleCo",
        job_description="Python, ML",
        fit_data=_fit_payload(),
        ats_score=75,
        truth_safe_ceiling=80,
    )
    item = qs.get_item_by_id(item_id)
    summary = qs.queue_row_summary(item)
    assert summary["company"] == "ExampleCo"
    assert summary["job_title"] == "ML Engineer"
    assert summary["job_url"]
    assert "recommended_action" in summary
