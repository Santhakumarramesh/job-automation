"""workspace_write_guard — Phase 4 tenant checks on enqueue payload."""

import pytest
from fastapi import HTTPException

from app.auth import User
from services.application_tracker import build_runner_tracker_metadata
from services.workspace_write_guard import (
    assert_ats_linkedin_caller_allowed,
    enforce_user_workspace_on_apply_jobs,
    enforce_user_workspace_on_job_payload,
    enforce_admin_workspace_on_read,
)


@pytest.fixture(autouse=True)
def _clear_guard_env(monkeypatch):
    monkeypatch.delenv("API_ENFORCE_USER_WORKSPACE_ON_WRITES", raising=False)
    monkeypatch.delenv("API_WORKSPACE_ENFORCE_FOR_ADMIN", raising=False)
    monkeypatch.delenv("API_ATS_LINKEDIN_REQUIRE_AUTH", raising=False)


def test_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("API_ENFORCE_USER_WORKSPACE_ON_WRITES", raising=False)
    p = {"workspace_id": "other"}
    enforce_user_workspace_on_job_payload(user=User("u", [], workspace_id="ws"), payload=p)
    assert p["workspace_id"] == "other"


def test_injects_workspace_when_empty(monkeypatch):
    monkeypatch.setenv("API_ENFORCE_USER_WORKSPACE_ON_WRITES", "1")
    p: dict = {}
    enforce_user_workspace_on_job_payload(user=User("u", [], workspace_id="ws-1"), payload=p)
    assert p["workspace_id"] == "ws-1"


def test_rejects_mismatch(monkeypatch):
    monkeypatch.setenv("API_ENFORCE_USER_WORKSPACE_ON_WRITES", "1")
    p = {"workspace_id": "ws-b"}
    with pytest.raises(HTTPException) as ei:
        enforce_user_workspace_on_job_payload(user=User("u", [], workspace_id="ws-a"), payload=p)
    assert ei.value.status_code == 403


def test_accepts_matching_workspace(monkeypatch):
    monkeypatch.setenv("API_ENFORCE_USER_WORKSPACE_ON_WRITES", "1")
    p = {"workspace_id": "ws-a"}
    enforce_user_workspace_on_job_payload(user=User("u", [], workspace_id="ws-a"), payload=p)
    assert p["workspace_id"] == "ws-a"


def test_organization_id_alone_must_match(monkeypatch):
    monkeypatch.setenv("API_ENFORCE_USER_WORKSPACE_ON_WRITES", "1")
    p = {"organization_id": "ws-a"}
    enforce_user_workspace_on_job_payload(user=User("u", [], workspace_id="ws-a"), payload=p)
    assert p.get("workspace_id") == "ws-a"


def test_conflicting_workspace_and_org_400(monkeypatch):
    monkeypatch.setenv("API_ENFORCE_USER_WORKSPACE_ON_WRITES", "1")
    p = {"workspace_id": "a", "organization_id": "b"}
    with pytest.raises(HTTPException) as ei:
        enforce_user_workspace_on_job_payload(user=User("u", [], workspace_id="a"), payload=p)
    assert ei.value.status_code == 400


def test_admin_exempt_by_default(monkeypatch):
    monkeypatch.setenv("API_ENFORCE_USER_WORKSPACE_ON_WRITES", "1")
    adm = User("admin", ["admin"], workspace_id="ws-a")
    p = {"workspace_id": "other"}
    enforce_user_workspace_on_job_payload(user=adm, payload=p)
    assert p["workspace_id"] == "other"


def test_admin_enforced_when_env(monkeypatch):
    monkeypatch.setenv("API_ENFORCE_USER_WORKSPACE_ON_WRITES", "1")
    monkeypatch.setenv("API_WORKSPACE_ENFORCE_FOR_ADMIN", "1")
    adm = User("admin", ["admin"], workspace_id="ws-a")
    p = {"workspace_id": "other"}
    with pytest.raises(HTTPException) as ei:
        enforce_user_workspace_on_job_payload(user=adm, payload=p)
    assert ei.value.status_code == 403


def test_assert_ats_rejects_demo_when_env(monkeypatch):
    monkeypatch.setenv("API_ATS_LINKEDIN_REQUIRE_AUTH", "1")
    with pytest.raises(HTTPException) as ei:
        assert_ats_linkedin_caller_allowed(User("demo-user", []))
    assert ei.value.status_code == 401


def test_enforce_apply_jobs_injects_user_and_workspace(monkeypatch):
    monkeypatch.setenv("API_ENFORCE_USER_WORKSPACE_ON_WRITES", "1")
    jobs = [{}]
    enforce_user_workspace_on_apply_jobs(
        user=User("alice", [], workspace_id="ws-1"),
        jobs=jobs,
        default_workspace_id=None,
    )
    assert jobs[0]["user_id"] == "alice"
    assert jobs[0]["workspace_id"] == "ws-1"


def test_enforce_apply_jobs_batch_default_workspace(monkeypatch):
    monkeypatch.setenv("API_ENFORCE_USER_WORKSPACE_ON_WRITES", "1")
    jobs = [{}]
    enforce_user_workspace_on_apply_jobs(
        user=User("alice", [], workspace_id="ws-1"),
        jobs=jobs,
        default_workspace_id="ws-1",
    )
    assert jobs[0]["workspace_id"] == "ws-1"


def test_admin_read_noop_when_env_disabled(monkeypatch):
    monkeypatch.delenv("API_WORKSPACE_ENFORCE_FOR_ADMIN", raising=False)
    adm = User("admin", ["admin"], workspace_id="ws-a")
    assert enforce_admin_workspace_on_read(admin=adm, query_workspace_id="ws-b") == "ws-b"
    assert enforce_admin_workspace_on_read(admin=adm, query_workspace_id=None) is None


def test_admin_read_enforced_defaults_to_admin_workspace(monkeypatch):
    monkeypatch.setenv("API_WORKSPACE_ENFORCE_FOR_ADMIN", "1")
    adm = User("admin", ["admin"], workspace_id="ws-a")
    assert enforce_admin_workspace_on_read(admin=adm, query_workspace_id=None) == "ws-a"
    assert enforce_admin_workspace_on_read(admin=adm, query_workspace_id=" ws-a ") == "ws-a"


def test_admin_read_rejects_mismatched_workspace(monkeypatch):
    monkeypatch.setenv("API_WORKSPACE_ENFORCE_FOR_ADMIN", "true")
    adm = User("admin", ["admin"], workspace_id="ws-a")
    with pytest.raises(HTTPException) as ei:
        enforce_admin_workspace_on_read(admin=adm, query_workspace_id="ws-b")
    assert ei.value.status_code == 403


def test_admin_read_falls_back_when_admin_has_no_workspace(monkeypatch):
    monkeypatch.setenv("API_WORKSPACE_ENFORCE_FOR_ADMIN", "1")
    adm = User("admin", ["admin"], workspace_id=None)
    assert enforce_admin_workspace_on_read(admin=adm, query_workspace_id="ws-b") == "ws-b"
    assert enforce_admin_workspace_on_read(admin=adm, query_workspace_id=None) is None


def test_build_runner_metadata_passes_identity_from_job():
    meta = build_runner_tracker_metadata(
        {
            "job_id": "j",
            "user_id": "u1",
            "workspace_id": "w9",
            "fit_decision": "apply",
        }
    )
    assert meta.get("user_id") == "u1"
    assert meta.get("workspace_id") == "w9"
