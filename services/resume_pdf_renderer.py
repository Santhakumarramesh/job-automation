"""
Phase 4 — Resume PDF Renderer
Converts HTML resume (from resume_designer.py) to a one-page PDF.

Strategy:
  1. Try WeasyPrint (best CSS→PDF fidelity)
  2. Fall back to pdfkit + wkhtmltopdf
  3. Fall back to reportlab plain-text PDF

After rendering, optionally calls resume_page_fit_engine.py to check page count
and compress if needed (Phase 5).
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESUME_OUTPUT_DIR = PROJECT_ROOT / "generated_resumes"


def render_html_to_pdf(
    html: str,
    output_path: Optional[str] = None,
    compress_to_one_page: bool = True,
) -> dict:
    """
    Render HTML resume to PDF.
    Returns {success, pdf_path, page_count, renderer_used, error}.
    """
    if output_path is None:
        RESUME_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = str(RESUME_OUTPUT_DIR / f"resume_{uuid.uuid4().hex[:8]}.pdf")

    # Try renderers in order
    for renderer_fn, renderer_name in [
        (_render_weasyprint, "weasyprint"),
        (_render_pdfkit, "pdfkit"),
        (_render_reportlab, "reportlab"),
    ]:
        try:
            result = renderer_fn(html, output_path)
            if result.get("success"):
                result["renderer_used"] = renderer_name

                # Check page count and compress if needed
                page_count = result.get("page_count", 1)
                if compress_to_one_page and page_count > 1:
                    from services.resume_page_fit_engine import compress_pdf_to_one_page
                    compress_result = compress_pdf_to_one_page(output_path, html=html)
                    if compress_result.get("success"):
                        result["page_count"] = compress_result.get("final_page_count", 1)
                        result["compression_applied"] = True
                        result["compression_steps"] = compress_result.get("steps_applied", [])

                return result
        except Exception as e:
            continue

    return {
        "success": False,
        "pdf_path": "",
        "page_count": 0,
        "renderer_used": "none",
        "error": "All PDF renderers failed. Install weasyprint or pdfkit.",
    }


def _render_weasyprint(html: str, output_path: str) -> dict:
    """Render using WeasyPrint — best CSS fidelity."""
    from weasyprint import HTML as WP_HTML  # type: ignore
    from weasyprint import CSS  # type: ignore

    # Force A4 page size
    css = CSS(string="""
        @page {
            size: A4;
            margin: 0;
        }
    """)

    doc = WP_HTML(string=html).render(stylesheets=[css])
    doc.write_pdf(output_path)

    page_count = len(doc.pages)
    return {"success": True, "pdf_path": output_path, "page_count": page_count}


def _render_pdfkit(html: str, output_path: str) -> dict:
    """Render using pdfkit + wkhtmltopdf."""
    import pdfkit  # type: ignore

    options = {
        "page-size": "A4",
        "margin-top": "0mm",
        "margin-right": "0mm",
        "margin-bottom": "0mm",
        "margin-left": "0mm",
        "encoding": "UTF-8",
        "no-outline": None,
        "quiet": "",
    }
    pdfkit.from_string(html, output_path, options=options)

    # Count pages by file size heuristic
    size = Path(output_path).stat().st_size
    page_count = max(1, size // 50000)
    return {"success": True, "pdf_path": output_path, "page_count": page_count}


def _render_reportlab(html: str, output_path: str) -> dict:
    """
    Fallback: plain-text PDF using reportlab.
    Strips HTML tags and writes text onto A4 page.
    """
    from reportlab.lib.pagesizes import A4  # type: ignore
    from reportlab.lib.styles import getSampleStyleSheet  # type: ignore
    from reportlab.lib.units import mm  # type: ignore
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer  # type: ignore
    import re

    # Strip HTML tags
    plain = re.sub(r"<[^>]+>", " ", html)
    plain = re.sub(r"\s+", " ", plain).strip()

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )
    styles = getSampleStyleSheet()
    story = [Paragraph(plain[:4000], styles["Normal"])]
    doc.build(story)

    return {"success": True, "pdf_path": output_path, "page_count": 1}


def get_page_count(pdf_path: str) -> int:
    """Count pages in a PDF file."""
    try:
        import pypdf  # type: ignore
        with open(pdf_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            return len(reader.pages)
    except ImportError:
        pass
    try:
        import pdfplumber  # type: ignore
        with pdfplumber.open(pdf_path) as pdf:
            return len(pdf.pages)
    except Exception:
        pass
    return 1
