#!/usr/bin/env python3
"""
Regenerate a resume PDF from markdown with proper alignment.
Usage: python scripts/regenerate_resume_pdf.py input.md output.pdf [candidate_name]
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
from agents.file_manager import build_styled_resume_pdf

def main():
    if len(sys.argv) < 3:
        print("Usage: python scripts/regenerate_resume_pdf.py input.md output.pdf [candidate_name]")
        print("Example: python scripts/regenerate_resume_pdf.py resume.md Santhakumar_Resume.pdf 'Santhakumar Ramesh'")
        sys.exit(1)
    inp = Path(sys.argv[1])
    out = Path(sys.argv[2])
    name = sys.argv[3] if len(sys.argv) > 3 else "Candidate"
    if not inp.exists():
        print(f"Error: {inp} not found")
        sys.exit(1)
    md = inp.read_text(encoding="utf-8")
    build_styled_resume_pdf(md, str(out), name)
    print(f"✓ Saved: {out}")

if __name__ == "__main__":
    main()
