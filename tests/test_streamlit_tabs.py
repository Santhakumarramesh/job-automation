#!/usr/bin/env python3
"""
Test all Streamlit app tabs for errors.
Run from project root: python tests/test_streamlit_tabs.py
"""
import os
import sys
from pathlib import Path

# Ensure project root is on path
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# Load env
from dotenv import load_dotenv

load_dotenv()


def _main() -> int:
    os.environ.setdefault("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", "sk-test"))
    os.environ.setdefault("APIFY_API_TOKEN", os.getenv("APIFY_API_TOKEN", os.getenv("APIFY_API_KEY", "apify_test")))

    errors: list[str] = []

    # Tab 1: Single Job - test PDF extraction (avoid full app import to reduce Streamlit noise)
    print("Tab 1: Single Job...")
    try:
        from pypdf import PdfReader
        import io

        def _extract_pdf(pdf_bytes):
            return "".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf_bytes)).pages)

        def extract_text_from_pdf(pdf_bytes):
            return _extract_pdf(pdf_bytes) if pdf_bytes else ""

        minimal_pdf = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000052 00000 n\n0000000101 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF"
        text = extract_text_from_pdf(minimal_pdf)
        assert isinstance(text, str), "extract_text_from_pdf should return str"
        print("  ✓ PDF extraction OK")
    except ImportError:
        try:
            import fitz

            minimal_pdf = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000052 00000 n\n0000000101 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF"
            text = "".join(p.get_text() for p in fitz.open(stream=minimal_pdf, filetype="pdf"))
            print("  ✓ PDF extraction OK (fitz)")
        except Exception as e2:
            errors.append(f"Tab 1: {e2}")
            print(f"  ✗ {e2}")
    except Exception as e:
        errors.append(f"Tab 1: {e}")
        print(f"  ✗ {e}")

    # Tab 2: Batch URL - test scrape
    print("Tab 2: Batch URL...")
    try:
        from ui.streamlit_app import scrape_job_url

        r = scrape_job_url("https://example.com")
        assert isinstance(r, str), "scrape_job_url should return str"
        print("  ✓ Scrape OK")
    except Exception as e:
        errors.append(f"Tab 2: {e}")
        print(f"  ✗ {e}")

    # Tab 3: AI Job Finder - test EnhancedJobFinder init
    print("Tab 3: AI Job Finder...")
    try:
        from services.enhanced_job_finder import EnhancedJobFinder

        EnhancedJobFinder(os.getenv("APIFY_API_TOKEN") or os.getenv("APIFY_API_KEY", "test"))
        print("  ✓ EnhancedJobFinder init OK")
    except Exception as e:
        errors.append(f"Tab 3: {e}")
        print(f"  ✗ {e}")

    # Tab 4: Application Tracker
    print("Tab 4: Application Tracker...")
    try:
        from services.application_tracker import load_applications

        df = load_applications()
        assert hasattr(df, "columns"), "load_applications should return DataFrame"
        print("  ✓ load_applications OK")
    except Exception as e:
        errors.append(f"Tab 4: {e}")
        print(f"  ✗ {e}")

    # LLM / ATS checker
    print("LLM / ATS Checker...")
    try:
        from enhanced_ats_checker import EnhancedATSChecker

        EnhancedATSChecker()
        print("  ✓ EnhancedATSChecker OK")
    except Exception as e:
        errors.append(f"ATS: {e}")
        print(f"  ✗ {e}")

    # Job Guard
    print("Job Guard...")
    try:
        from agents.job_guard import guard_job_quality

        state = {"job_description": "Legitimate Data Analyst role at Tech Corp. Python, SQL required."}
        out = guard_job_quality(state)
        assert "is_eligible" in out, "guard_job_quality should return is_eligible"
        print("  ✓ Job Guard OK")
    except Exception as e:
        errors.append(f"Job Guard: {e}")
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
