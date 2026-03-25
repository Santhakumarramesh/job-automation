"""role_templates — JWT role template expansion (Phase 4)."""

import pytest


@pytest.fixture(autouse=True)
def _clear_template_env(monkeypatch):
    monkeypatch.delenv("JWT_ROLE_TEMPLATE_MAP", raising=False)


def test_expand_appends_mapped_roles(monkeypatch):
    monkeypatch.setenv(
        "JWT_ROLE_TEMPLATE_MAP",
        '{"ops": ["approver", "auditor"], "empty": []}',
    )
    from services.role_templates import expand_roles_from_template

    out = expand_roles_from_template(["viewer"], "ops")
    assert "viewer" in out
    assert "approver" in out
    assert "auditor" in out


def test_unknown_template_noop():
    from services.role_templates import expand_roles_from_template

    assert expand_roles_from_template(["a"], "nope") == ["a"]


def test_normalize_claim():
    from services.role_templates import normalize_role_template_claim

    assert normalize_role_template_claim(None) is None
    assert normalize_role_template_claim("  X  ") == "X"
