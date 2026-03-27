"""
Portal resume state detection helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import re

_FILENAME_RE = re.compile(r"([A-Za-z0-9][A-Za-z0-9 _\-\.]*\.(?:pdf|docx?|rtf|txt))", re.I)
_SIZE_RE = re.compile(r"\s*\(\s*\d+(?:\.\d+)?\s*(?:kb|mb)\s*\)\s*$", re.I)


def extract_filename(text: str) -> str:
    if not text:
        return ""
    match = _FILENAME_RE.search(text)
    if not match:
        return ""
    return match.group(1).strip()


def normalize_filename(name: str) -> str:
    if not name:
        return ""
    base = extract_filename(name) or str(name)
    base = base.strip().strip('"\'')
    base = os.path.basename(base)
    base = _SIZE_RE.sub("", base)
    return base.strip().lower()


@dataclass
class PortalResumeState:
    resume_slot_present: bool
    upload_control_found: bool
    existing_resume_detected: bool
    existing_resume_filename: str = ""
    can_remove_existing_resume: bool = False
    can_replace_existing_resume: bool = False

    def matches_filename(self, expected_filename: str) -> bool:
        return normalize_filename(self.existing_resume_filename) == normalize_filename(expected_filename)

    def as_dict(self) -> dict:
        return {
            "resume_slot_present": bool(self.resume_slot_present),
            "upload_control_found": bool(self.upload_control_found),
            "existing_resume_detected": bool(self.existing_resume_detected),
            "existing_resume_filename": self.existing_resume_filename or "",
            "can_remove_existing_resume": bool(self.can_remove_existing_resume),
            "can_replace_existing_resume": bool(self.can_replace_existing_resume),
        }
