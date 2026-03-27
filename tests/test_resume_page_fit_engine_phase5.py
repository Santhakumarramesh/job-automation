from __future__ import annotations

from types import SimpleNamespace

from services.resume_designer import ResumeContent
from services import resume_page_fit_engine as fit_engine


def _content_with_bullets() -> ResumeContent:
    return ResumeContent(
        full_name="Jane Doe",
        email="jane@example.com",
        phone="555-0100",
        location="Remote",
        target_title="ML Engineer",
        summary="Experienced engineer building AI systems. " * 8,
        work_experiences=[
            {
                "title": "Engineer",
                "company": "ExampleCo",
                "start": "2021-01",
                "end": "2022-12",
                "bullets": [
                    "Improved model accuracy by 12% using feature engineering.",
                    "Worked on tasks for the team.",
                ],
            }
        ],
        projects=[],
        skills={"Languages": ["Python"]},
        education=[],
    )


def test_fit_engine_compresses_to_one_page(monkeypatch):
    calls = {"n": 0}

    def _stub_render(content, template, template_id, output_path, render_pdf=True):
        calls["n"] += 1
        page_count = 2 if calls["n"] < 3 else 1
        dummy = SimpleNamespace(
            html="html",
            rendered_pdf_path="/tmp/resume.pdf",
            page_count=page_count,
            estimated_page_count=page_count,
            resume_version_id="res1",
        )
        return dummy, page_count

    monkeypatch.setattr(fit_engine, "_render_for_fit", _stub_render)
    out = fit_engine.fit_resume_to_one_page(_content_with_bullets(), template_id="classic_ats")
    assert out["fit_passed"] is True
    assert out["final_page_count"] == 1
    assert out["compression_steps_applied"]


def test_fit_engine_respects_minimums(monkeypatch):
    def _stub_render(content, template, template_id, output_path, render_pdf=True):
        dummy = SimpleNamespace(
            html="html",
            rendered_pdf_path="/tmp/resume.pdf",
            page_count=2,
            estimated_page_count=2,
            resume_version_id="res2",
        )
        return dummy, 2

    monkeypatch.setattr(fit_engine, "_render_for_fit", _stub_render)
    content = _content_with_bullets()
    out = fit_engine.fit_resume_to_one_page(content, template_id="compact_ats")
    template = out["final_template"]
    assert template["font_size_body"] >= fit_engine.MIN_TEMPLATE["font_size_body"]
    assert template["line_height"] >= fit_engine.MIN_TEMPLATE["line_height"]


def test_fit_engine_logs_trimming(monkeypatch):
    def _stub_render(content, template, template_id, output_path, render_pdf=True):
        total = sum(len(e.get("bullets", [])) for e in content.work_experiences)
        page_count = 1 if total <= 1 else 2
        dummy = SimpleNamespace(
            html="html",
            rendered_pdf_path="/tmp/resume.pdf",
            page_count=page_count,
            estimated_page_count=page_count,
            resume_version_id="res3",
        )
        return dummy, page_count

    monkeypatch.setattr(fit_engine, "_render_for_fit", _stub_render)
    out = fit_engine.fit_resume_to_one_page(_content_with_bullets(), template_id="classic_ats")
    assert any(entry["action"] in ("summary_trim", "trim_bullet") for entry in out["trimmed_content_log"])


def test_fit_engine_trims_low_value_bullet_first(monkeypatch):
    def _stub_render(content, template, template_id, output_path, render_pdf=True):
        total = sum(len(e.get("bullets", [])) for e in content.work_experiences)
        page_count = 1 if total <= 1 else 2
        dummy = SimpleNamespace(
            html="html",
            rendered_pdf_path="/tmp/resume.pdf",
            page_count=page_count,
            estimated_page_count=page_count,
            resume_version_id="res4",
        )
        return dummy, page_count

    monkeypatch.setattr(fit_engine, "_render_for_fit", _stub_render)
    out = fit_engine.fit_resume_to_one_page(_content_with_bullets(), template_id="classic_ats")
    trim_entries = [e for e in out["trimmed_content_log"] if e.get("action") == "trim_bullet"]
    assert trim_entries
    assert "Worked on tasks" in trim_entries[0]["removed"]
