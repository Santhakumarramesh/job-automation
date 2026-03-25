#!/usr/bin/env python3
"""
Smoke checks for Streamlit tab dependencies and helpers.

Run with pytest: ``pytest tests/test_streamlit_tabs.py``
Or directly: ``python tests/test_streamlit_tabs.py``
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from dotenv import load_dotenv

# Ensure project root is on path
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

load_dotenv()

_MINIMAL_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
    b"xref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000052 00000 n\n"
    b"0000000101 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF"
)


def _ensure_tab_test_env() -> None:
    os.environ.setdefault("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", "sk-test"))
    os.environ.setdefault(
        "APIFY_API_TOKEN",
        os.getenv("APIFY_API_TOKEN", os.getenv("APIFY_API_KEY", "apify_test")),
    )


def _check_pdf_extraction() -> None:
    try:
        from pypdf import PdfReader

        def _extract_pdf(pdf_bytes: bytes) -> str:
            return "".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf_bytes)).pages)

        text = _extract_pdf(_MINIMAL_PDF) if _MINIMAL_PDF else ""
        assert isinstance(text, str), "extract should return str"
    except ImportError:
        import fitz

        text = "".join(p.get_text() for p in fitz.open(stream=_MINIMAL_PDF, filetype="pdf"))
        assert isinstance(text, str), "fitz extract should return str"


def _check_scrape_job_url() -> None:
    from ui.streamlit_app import scrape_job_url

    r = scrape_job_url("https://example.com")
    assert isinstance(r, str), "scrape_job_url should return str"


def _check_enhanced_job_finder_init() -> None:
    from services.enhanced_job_finder import EnhancedJobFinder

    EnhancedJobFinder(os.getenv("APIFY_API_TOKEN") or os.getenv("APIFY_API_KEY", "test"))


def _check_career_api_helpers() -> None:
    from ui.streamlit_app import (
        _career_api_base_default,
        _career_api_bearer_default,
        _career_api_call,
        _career_api_headers,
    )

    assert _career_api_base_default().startswith("http")
    assert isinstance(_career_api_bearer_default(), str)
    assert "Content-Type" not in _career_api_headers("")
    h = _career_api_headers("secret", for_json_body=True)
    assert h.get("X-API-Key") == "secret"
    assert h.get("Content-Type") == "application/json"
    hb = _career_api_headers("", bearer="tok", for_json_body=True)
    assert hb.get("Authorization") == "Bearer tok"
    assert hb.get("Content-Type") == "application/json"
    h2 = _career_api_headers("k", bearer="Bearer already", for_json_body=False)
    assert h2.get("Authorization") == "Bearer already"
    assert h2.get("X-API-Key") == "k"

    with patch("ui.streamlit_app.requests.post") as mock_post:
        mock_post.return_value.status_code = 202
        mock_post.return_value.json.return_value = {"job_id": "x", "status": "accepted"}
        _career_api_call(
            "http://test",
            "POST",
            "/api/jobs",
            api_key="k",
            json_body={"name": "n", "payload": {}},
            extra_headers={"Idempotency-Key": "idem-1"},
            timeout=5.0,
        )
        hdrs = mock_post.call_args.kwargs.get("headers") or {}
        assert hdrs.get("Idempotency-Key") == "idem-1"
        assert hdrs.get("X-API-Key") == "k"
    with patch("ui.streamlit_app.requests.patch") as mock_patch:
        mock_patch.return_value.status_code = 200
        mock_patch.return_value.json.return_value = {"ok": True}
        _career_api_call(
            "http://test",
            "PATCH",
            "/api/applications/x/follow-up",
            api_key="k2",
            json_body={"follow_up_status": "pending"},
            timeout=5.0,
        )
        ph = mock_patch.call_args.kwargs.get("headers") or {}
        assert ph.get("Content-Type") == "application/json"
        assert ph.get("X-API-Key") == "k2"
    with patch("ui.streamlit_app.requests.delete") as mock_delete:
        mock_delete.return_value.status_code = 200
        mock_delete.return_value.json.return_value = {"deleted": 1}
        _career_api_call(
            "http://test",
            "DELETE",
            "/api/admin/applications/by-user",
            api_key="k3",
            params={"user_id": "alice", "confirm_user_id": "alice"},
            timeout=5.0,
        )
        dh = mock_delete.call_args.kwargs.get("headers") or {}
        assert dh.get("X-API-Key") == "k3"
        assert mock_delete.call_args.kwargs.get("params", {}).get("user_id") == "alice"


def _check_load_applications() -> None:
    from services.application_tracker import load_applications

    df = load_applications()
    assert hasattr(df, "columns"), "load_applications should return DataFrame"


def _check_enhanced_ats_checker_init() -> None:
    from enhanced_ats_checker import EnhancedATSChecker

    EnhancedATSChecker()


def _check_job_guard_heuristic_block() -> None:
    from agents.job_guard import guard_job_quality

    out = guard_job_quality({"job_description": "Senior role requiring 15+ years experience in Python."})
    assert out.get("is_eligible") is False


def _check_job_guard_mocked_llm_pass() -> None:
    mock_inst = MagicMock()
    mock_inst.invoke.return_value = MagicMock(content='{"is_scam": false, "reason": "legitimate"}')
    with patch("agents.job_guard.ChatOpenAI", return_value=mock_inst):
        from agents.job_guard import guard_job_quality

        state = {
            "job_description": "Legitimate Data Analyst role at Tech Corp. Python, SQL required.",
        }
        out = guard_job_quality(state)
        assert out.get("is_eligible") is True


def test_streamlit_tab_pdf_extraction() -> None:
    _ensure_tab_test_env()
    _check_pdf_extraction()


def test_streamlit_tab_scrape_job_url() -> None:
    _ensure_tab_test_env()
    _check_scrape_job_url()


def test_streamlit_tab_enhanced_job_finder_init() -> None:
    _ensure_tab_test_env()
    _check_enhanced_job_finder_init()


def test_streamlit_career_api_helpers() -> None:
    _ensure_tab_test_env()
    _check_career_api_helpers()


def test_streamlit_load_applications() -> None:
    _ensure_tab_test_env()
    _check_load_applications()


def test_streamlit_enhanced_ats_checker_init() -> None:
    _ensure_tab_test_env()
    _check_enhanced_ats_checker_init()


def test_job_guard_blocks_extreme_seniority_heuristic() -> None:
    _ensure_tab_test_env()
    _check_job_guard_heuristic_block()


def test_job_guard_passes_with_mocked_llm() -> None:
    _ensure_tab_test_env()
    _check_job_guard_mocked_llm_pass()


def _main() -> int:
    _ensure_tab_test_env()
    errors: list[str] = []
    checks: list[tuple[str, object]] = [
        ("Tab 1: Single Job", _check_pdf_extraction),
        ("Tab 2: Batch URL", _check_scrape_job_url),
        ("Tab 3: AI Job Finder", _check_enhanced_job_finder_init),
        ("Career API helpers", _check_career_api_helpers),
        ("Tab 4: Application Tracker", _check_load_applications),
        ("LLM / ATS Checker", _check_enhanced_ats_checker_init),
        ("Job Guard (heuristic)", _check_job_guard_heuristic_block),
        ("Job Guard (mocked LLM)", _check_job_guard_mocked_llm_pass),
    ]
    for label, fn in checks:
        print(f"{label}...")
        try:
            fn()
            print("  ✓ OK")
        except Exception as e:
            errors.append(f"{label}: {e}")
            print(f"  ✗ {e}")
    print("\n" + "=" * 50)
    if errors:
        print("ERRORS:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("All tabs OK – no errors.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
