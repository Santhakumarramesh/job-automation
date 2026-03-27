"""
Phase 4 — Resume Template Rules
Central, deterministic template config for ATS-safe resume rendering.
"""

from __future__ import annotations

DEFAULT_TEMPLATE_ID = "classic_ats"
ATS_SAFE_FONT_STACK = "Arial, Helvetica, sans-serif"

TEMPLATE_RULES: dict[str, dict] = {
    "classic_ats": {
        "description": "Traditional chronological — maximum ATS compatibility",
        "font_size_body": 10,
        "font_size_heading": 13,
        "font_size_name": 20,
        "line_height": 1.4,
        "margin_top": 22,
        "margin_side": 22,
        "section_spacing": 10,
        "bullet_spacing": 3,
        "section_order": ["summary", "experience", "projects", "skills", "education"],
    },
    "compact_ats": {
        "description": "Tighter spacing — fits more content on one page",
        "font_size_body": 9.5,
        "font_size_heading": 12,
        "font_size_name": 18,
        "line_height": 1.3,
        "margin_top": 16,
        "margin_side": 18,
        "section_spacing": 7,
        "bullet_spacing": 2,
        "section_order": ["summary", "experience", "projects", "skills", "education"],
    },
    "technical_ats": {
        "description": "Skills-first layout for engineering roles",
        "font_size_body": 10,
        "font_size_heading": 13,
        "font_size_name": 20,
        "line_height": 1.4,
        "margin_top": 22,
        "margin_side": 22,
        "section_spacing": 10,
        "bullet_spacing": 3,
        "section_order": ["summary", "skills", "experience", "projects", "education"],
    },
}


def get_template(template_id: str) -> dict:
    tid = str(template_id or "").strip() or DEFAULT_TEMPLATE_ID
    return TEMPLATE_RULES.get(tid, TEMPLATE_RULES[DEFAULT_TEMPLATE_ID])


def list_templates() -> list[str]:
    return list(TEMPLATE_RULES.keys())
