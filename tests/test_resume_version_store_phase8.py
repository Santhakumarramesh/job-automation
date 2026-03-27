from __future__ import annotations

from pathlib import Path

import pytest

from services import resume_version_store as rvs
from services import resume_upload_binding as rub
from services import apply_queue_service as qs


@pytest.fixture
def queue_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setattr(qs, "DB_PATH", db_path)
    monkeypatch.setattr(rvs, "DB_PATH", db_path)
    return db_path


def test_create_and_lookup_resume_version(queue_db: Path, tmp_path: Path):
    pdf_path = tmp_path / "resume.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%EOF\n")
    version = rvs.create_resume_version(
        approved_pdf_path=str(pdf_path),
        approved_by="tester",
        template_id="classic_ats",
        page_count=1,
        layout_status="fits_one_page",
    )
    fetched = rvs.get_resume_version(version["resume_version_id"])
    assert fetched
    assert fetched["approved_pdf_path"] == str(pdf_path)


def test_bind_resume_to_queue_item(queue_db: Path, tmp_path: Path):
    item_id = qs.upsert_queue_item(
        job_url="https://example.com/job/1",
        job_title="ML Engineer",
        company="ExampleCo",
        job_description="Python, ML",
        fit_data={"fit_decision": "apply", "overall_fit_score": 70},
    )
    pdf_path = tmp_path / "resume.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%EOF\n")

    version = rub.bind_approved_resume(
        item_id,
        approved_pdf_path=str(pdf_path),
        approved_by="tester",
        template_id="classic_ats",
    )
    item = qs.get_item_by_id(item_id)
    assert item.get("approved_resume_version_id") == version["resume_version_id"]
    assert item.get("approved_resume_path") == str(pdf_path)


def test_get_bound_resume_for_queue_item(queue_db: Path, tmp_path: Path):
    item_id = qs.upsert_queue_item(
        job_url="https://example.com/job/2",
        job_title="ML Engineer",
        company="ExampleCo",
        job_description="Python, ML",
        fit_data={"fit_decision": "apply", "overall_fit_score": 70},
    )
    pdf_path = tmp_path / "resume.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%EOF\n")
    rub.bind_approved_resume(item_id, approved_pdf_path=str(pdf_path))
    result = rub.get_bound_resume_for_queue_item(item_id)
    assert result["status"] == "ok"
    assert result["version"]["approved_pdf_path"] == str(pdf_path)


def test_missing_bound_resume_blocks(queue_db: Path):
    item_id = qs.upsert_queue_item(
        job_url="https://example.com/job/3",
        job_title="ML Engineer",
        company="ExampleCo",
        job_description="Python, ML",
        fit_data={"fit_decision": "apply", "overall_fit_score": 70},
    )
    result = rub.ensure_bound_resume_or_block(item_id)
    assert result["status"] == "error"
    item = qs.get_item_by_id(item_id)
    assert item["job_state"] == qs.JobQueueState.BLOCKED
