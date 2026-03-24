"""Live form probe (URL validation; mocked Playwright for DOM path)."""

import importlib.util
from unittest.mock import MagicMock, patch

import pytest

from services.live_form_probe import (
    _allowed_http_url,
    live_form_probe_disabled_response,
    probe_apply_page_fields,
)


def test_allowed_http_url():
    assert _allowed_http_url("https://boards.greenhouse.io/x/jobs/1") is True
    assert _allowed_http_url("http://127.0.0.1:8000/apply") is True
    assert _allowed_http_url("file:///etc/passwd") is False
    assert _allowed_http_url("") is False


def test_live_form_probe_disabled_response_shape():
    d = live_form_probe_disabled_response()
    assert d["status"] == "disabled"
    assert "ATS_ALLOW_LIVE_FORM_PROBE" in d["message"]


def test_probe_empty_url():
    r = probe_apply_page_fields("")
    assert r["status"] == "error"
    assert r["field_count"] == 0


def test_probe_disallowed_scheme():
    r = probe_apply_page_fields("javascript:alert(1)")
    assert r["status"] == "error"


def test_probe_playwright_import_error():
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "playwright.sync_api":
            raise ImportError("no playwright")
        return real_import(name, *args, **kwargs)

    with patch.object(builtins, "__import__", fake_import):
        r = probe_apply_page_fields("https://boards.example.com/jobs/1")

    assert r["status"] == "error"
    assert "playwright" in r["message"].lower()


@pytest.mark.skipif(
    importlib.util.find_spec("playwright") is None,
    reason="playwright not installed",
)
def test_probe_dom_path_mocked():
    """No browser or network: patch sync_playwright context manager."""
    fake_el = MagicMock()
    fake_el.evaluate.return_value = "input"
    fake_el.get_attribute.side_effect = lambda n: {
        "type": "email",
        "name": "work_email",
        "id": "e1",
        "placeholder": "",
        "aria-label": "",
        "required": None,
    }.get(n)

    fake_page = MagicMock()
    fake_page.title.return_value = "Apply — ACME"
    fake_page.url = "https://boards.example.com/jobs/1"
    fake_page.query_selector_all.return_value = [fake_el]

    fake_context = MagicMock()
    fake_context.new_page.return_value = fake_page

    fake_browser = MagicMock()
    fake_browser.new_context.return_value = fake_context

    p_root = MagicMock()
    p_root.chromium.launch.return_value = fake_browser

    cm = MagicMock()
    cm.__enter__.return_value = p_root
    cm.__exit__.return_value = False

    with patch("playwright.sync_api.sync_playwright", return_value=cm):
        r = probe_apply_page_fields("https://boards.example.com/jobs/1", max_fields=10)

    assert r["status"] == "ok"
    assert r["field_count"] == 1
    assert r["fields"][0]["name"] == "work_email"
    assert r["fields"][0]["type"] == "email"
    fake_browser.close.assert_called()
