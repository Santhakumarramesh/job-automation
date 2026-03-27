from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest


def _install_fastmcp_stub() -> None:
    mod = types.ModuleType("fastmcp")

    class _StubMCP:
        def __init__(self, *args, **kwargs):
            pass

        def tool(self):
            def _decorator(fn):
                return fn

            return _decorator

    mod.FastMCP = _StubMCP
    sys.modules["fastmcp"] = mod


def test_evaluate_job_and_prepare_action_plan(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    _install_fastmcp_stub()
    server = importlib.import_module("mcp_servers.job_apply_autofill.server")

    class _StubATSChecker:
        def comprehensive_ats_check(self, **kwargs):
            return {"ats_score": 88}

    import enhanced_ats_checker

    monkeypatch.setattr(enhanced_ats_checker, "EnhancedATSChecker", _StubATSChecker)

    def _stub_generate_package_for_job(*args, **kwargs):
        return {
            "resume_version_id": "res_test",
            "package_status": "generated",
            "initial_ats_score": 70,
            "final_ats_score": 80,
            "truth_safe_ats_ceiling": 85,
            "resume_path": str(tmp_path / "resume.pdf"),
        }

    import services.resume_package_service as rps

    monkeypatch.setattr(rps, "generate_package_for_job", _stub_generate_package_for_job)

    job = {
        "url": "https://www.linkedin.com/jobs/view/123",
        "title": "ML Engineer",
        "company": "ExampleCo",
        "description": "Python, ML, AWS",
        "location": "Remote",
    }

    out = server.evaluate_job_and_prepare_action_plan(
        job_json=job,
        master_resume_text="SUMMARY\nTest\nEXPERIENCE\n- Bullet",
        include_package=True,
        render_one_page_pdf=False,
    )

    assert out["status"] == "ok"
    assert out["normalized_job"]["company"] == "ExampleCo"
    assert out["fit"]["fit_decision"] in ("apply", "review_fit", "reject", "skip")
    assert out["ats_score"] == 88
    assert out["answer_risk_summary"]["counts"]
    assert out["package_artifacts"]["resume_version_id"] == "res_test"
