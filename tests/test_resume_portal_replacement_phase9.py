"""Phase 9: Portal resume replacement engine."""

import json
import os
import pytest

from services.portal_resume_state import PortalResumeState
from services.resume_upload_verifier import ensure_portal_resume
from services.resume_portal_adapter import ResumePortalAdapter


class _FakeAdapter(ResumePortalAdapter):
    def __init__(
        self,
        state: PortalResumeState,
        *,
        verify_ok: bool = True,
        upload_ok: bool = True,
        remove_ok: bool = True,
    ) -> None:
        self.state = state
        self.verify_ok = verify_ok
        self.upload_ok = upload_ok
        self.remove_ok = remove_ok
        self.calls: list[str] = []

    async def detect_state(self, page):
        self.calls.append("detect_state")
        return self.state

    async def get_current_resume(self, page):
        self.calls.append("get_current_resume")
        return {
            "filename": self.state.existing_resume_filename,
            "detected": self.state.existing_resume_detected,
        }

    async def remove_current_resume(self, page):
        self.calls.append("remove")
        if self.remove_ok:
            self.state.existing_resume_detected = False
            self.state.existing_resume_filename = ""
        return self.remove_ok

    async def upload_resume(self, page, resume_path: str):
        self.calls.append("upload")
        if self.upload_ok:
            self.state.existing_resume_detected = True
            self.state.existing_resume_filename = os.path.basename(resume_path)
        return self.upload_ok

    async def verify_uploaded_resume(self, page, expected_filename: str):
        self.calls.append("verify")
        return self.verify_ok and self.state.matches_filename(expected_filename)


@pytest.mark.asyncio
async def test_resume_already_correct(tmp_path):
    resume_path = tmp_path / "Jane_Doe_Resume.pdf"
    resume_path.write_text("resume")

    state = PortalResumeState(
        resume_slot_present=True,
        upload_control_found=True,
        existing_resume_detected=True,
        existing_resume_filename="Jane_Doe_Resume.pdf",
        can_remove_existing_resume=True,
        can_replace_existing_resume=True,
    )
    adapter = _FakeAdapter(state)

    result = await ensure_portal_resume(None, str(resume_path), adapter=adapter)
    assert result["status"] == "ok"
    assert result["action"] == "already_correct"
    assert "upload" not in adapter.calls


@pytest.mark.asyncio
async def test_wrong_resume_replaced(tmp_path):
    resume_path = tmp_path / "New_Resume.pdf"
    resume_path.write_text("resume")

    state = PortalResumeState(
        resume_slot_present=True,
        upload_control_found=True,
        existing_resume_detected=True,
        existing_resume_filename="Old_Resume.pdf",
        can_remove_existing_resume=True,
        can_replace_existing_resume=True,
    )
    adapter = _FakeAdapter(state)

    result = await ensure_portal_resume(None, str(resume_path), adapter=adapter)
    assert result["status"] == "ok"
    assert result["action"] == "removed_then_uploaded"
    assert "remove" in adapter.calls
    assert "upload" in adapter.calls


@pytest.mark.asyncio
async def test_resume_audit_events_emitted(tmp_path, monkeypatch: pytest.MonkeyPatch):
    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setenv("AUDIT_LOG_PATH", str(audit_path))

    resume_path = tmp_path / "New_Resume.pdf"
    resume_path.write_text("resume")

    state = PortalResumeState(
        resume_slot_present=True,
        upload_control_found=True,
        existing_resume_detected=True,
        existing_resume_filename="Old_Resume.pdf",
        can_remove_existing_resume=True,
        can_replace_existing_resume=True,
    )
    adapter = _FakeAdapter(state)

    result = await ensure_portal_resume(
        None,
        str(resume_path),
        adapter=adapter,
        audit_context={"job_id": "jid1", "company": "ExampleCo", "position": "ML Eng"},
    )
    assert result["status"] == "ok"
    assert audit_path.exists()
    actions = [json.loads(line)["action"] for line in audit_path.read_text().splitlines()]
    assert "resume_detected_existing" in actions
    assert "resume_removed_existing" in actions
    assert "resume_uploaded_new" in actions
    assert "resume_verified" in actions


@pytest.mark.asyncio
async def test_verification_failure_blocks(tmp_path):
    resume_path = tmp_path / "Candidate_Resume.pdf"
    resume_path.write_text("resume")

    state = PortalResumeState(
        resume_slot_present=True,
        upload_control_found=True,
        existing_resume_detected=False,
        existing_resume_filename="",
        can_remove_existing_resume=False,
        can_replace_existing_resume=True,
    )
    adapter = _FakeAdapter(state, verify_ok=False)

    result = await ensure_portal_resume(None, str(resume_path), adapter=adapter)
    assert result["status"] == "blocked"
    assert result["error"] == "resume_verification_failed"


@pytest.mark.asyncio
async def test_missing_upload_control_blocks(tmp_path):
    resume_path = tmp_path / "Candidate_Resume.pdf"
    resume_path.write_text("resume")

    state = PortalResumeState(
        resume_slot_present=True,
        upload_control_found=False,
        existing_resume_detected=False,
        existing_resume_filename="",
        can_remove_existing_resume=False,
        can_replace_existing_resume=False,
    )
    adapter = _FakeAdapter(state)

    result = await ensure_portal_resume(None, str(resume_path), adapter=adapter)
    assert result["status"] == "blocked"
    assert result["error"] == "upload_control_not_found"
