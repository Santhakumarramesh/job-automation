"""workspace_write_guard — Phase 4 tenant checks on enqueue payload."""

import pytest
from fastapi import HTTPException

from app.auth import User
from services.workspace_write_guard import enforce_user_workspace_on_job_payload


@pytest.fixture(autouse=True)
def _clear_guard_env(monkeypatch):
    monkeypatch.delenv("API_ENFORCE_USER_WORKSPACE_ON_WRITES", raising=False)
    monkeypatch.delenv("API_WORKSPACE_ENFORCE_FOR_ADMIN", raising=False)


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
