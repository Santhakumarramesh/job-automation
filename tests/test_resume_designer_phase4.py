from __future__ import annotations

from pathlib import Path

import pytest

from services.resume_designer import ResumeContent, design_resume, render_one_page_resume


def _sample_content() -> ResumeContent:
    return ResumeContent(
        full_name="Jane Doe",
        email="jane@example.com",
        phone="555-0100",
        linkedin="https://linkedin.com/in/jane",
        github="https://github.com/jane",
        location="Remote",
        target_title="Machine Learning Engineer",
        summary="Machine learning engineer building production NLP systems.",
        work_experiences=[
            {
                "title": "ML Engineer",
                "company": "ExampleCo",
                "start": "2021-03",
                "end": "2022-11",
                "bullets": ["Built RAG pipelines.", "Deployed models to production."],
            }
        ],
        projects=[
            {"name": "Vector Search", "tech_stack": "Python, Pinecone", "bullets": ["Optimized retrieval."]},
        ],
        skills={"Languages": ["Python"], "ML / AI": ["Rag", "Pytorch"]},
        education=[{"degree": "MS Computer Science", "school": "Example University", "graduation": "2020"}],
    )


@pytest.mark.parametrize("template_id", ["classic_ats", "compact_ats", "technical_ats"])
def test_design_resume_templates_render(template_id: str):
    content = _sample_content()
    result = design_resume(content, template_id=template_id)
    assert "SUMMARY" in result.html
    assert "EXPERIENCE" in result.html
    assert "SKILLS" in result.html
    assert result.template_id == template_id

    if template_id == "technical_ats":
        assert result.html.index("SKILLS") < result.html.index("EXPERIENCE")


def test_design_resume_normalizes_dates():
    content = _sample_content()
    result = design_resume(content, template_id="classic_ats")
    assert "Mar 2021" in result.html
    assert "Nov 2022" in result.html


def test_render_one_page_resume_writes_pdf(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from services import resume_pdf_renderer

    def _stub_render(html: str, output_path: str | None = None, compress_to_one_page: bool = True):
        path = Path(output_path or tmp_path / "resume.pdf")
        path.write_bytes(b"%PDF-1.4\n%EOF\n")
        return {"success": True, "pdf_path": str(path), "page_count": 1, "renderer_used": "stub"}

    monkeypatch.setattr(resume_pdf_renderer, "render_html_to_pdf", _stub_render)

    out = render_one_page_resume(
        master_resume_text="SUMMARY\nTest\nEXPERIENCE\n- Bullet",
        job_title="ML Engineer",
        company="ExampleCo",
        job_description="Python, ML",
        template_id="classic_ats",
        resume_text_override="SUMMARY\nTest\nEXPERIENCE\n- Bullet",
        output_path=str(tmp_path / "one_page.pdf"),
    )
    assert out["rendered_pdf_path"]
    assert Path(out["rendered_pdf_path"]).exists()
    assert out["page_count"] == 1
