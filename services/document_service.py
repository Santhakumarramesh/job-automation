"""
Document service. tailor, humanize, build PDFs.
"""

import io
from typing import Optional

# PDF extraction - try PyMuPDF first, fallback to pypdf
try:
    import fitz  # PyMuPDF

    def _extract_pdf(pdf_bytes):
        return "".join(page.get_text() for page in fitz.open(stream=pdf_bytes, filetype="pdf"))
except ImportError:
    try:
        from pypdf import PdfReader

        def _extract_pdf(pdf_bytes):
            return "".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf_bytes)).pages)
    except ImportError:

        def _extract_pdf(pdf_bytes):
            raise ImportError(
                "PDF support required. Run: pip install pymupdf  (or: pip install pypdf)\n"
                "If using venv: source venv/bin/activate && pip install pymupdf"
            )

from agents.resume_editor import tailor_resume
from agents.humanize_resume import humanize_resume
from agents.humanize_cover_letter import humanize_cover_letter
from agents.cover_letter_generator import generate_cover_letter
from agents.file_manager import save_documents


def extract_text_from_pdf(pdf_bytes: Optional[bytes]) -> str:
    """Extract text from PDF bytes. Returns empty string if None."""
    if pdf_bytes is None:
        return ""
    return _extract_pdf(pdf_bytes)


def tailor(state: dict) -> dict:
    """Tailor resume to job. Returns state with tailored_resume_text."""
    return tailor_resume(state)


def humanize_resume_text(state: dict) -> dict:
    """Humanize resume. Returns state with humanized_resume_text."""
    return humanize_resume(state)


def generate_cover_letter_from_state(state: dict) -> dict:
    """Generate cover letter. Returns state with cover_letter_text."""
    return generate_cover_letter(state)


def humanize_cover_letter_text(state: dict) -> dict:
    """Humanize cover letter. Returns state with humanized_cover_letter_text."""
    return humanize_cover_letter(state)


def save_documents_to_pdf(state: dict) -> dict:
    """Save resume and cover letter as PDFs. Returns state with final_pdf_path, cover_letter_pdf_path."""
    return save_documents(state)
