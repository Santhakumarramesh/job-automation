"""
Phase 5 — Fit-to-One-Page Compression Engine
Deterministically compress ATS resume layouts to fit on one page.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Optional, Tuple

from services.resume_designer import ResumeContent, design_resume
from services.resume_template_rules import get_template

try:
    from enhanced_ats_checker import ACTION_VERBS
except Exception:
    ACTION_VERBS = []


MIN_TEMPLATE = {
    "section_spacing": 4,
    "bullet_spacing": 1,
    "margin_top": 12,
    "margin_side": 12,
    "line_height": 1.2,
    "font_size_body": 9.0,
    "font_size_heading": 11.0,
    "font_size_name": 16.0,
}


def fit_resume_to_one_page(
    content: ResumeContent,
    template_id: str = "classic_ats",
    output_path: Optional[str] = None,
    *,
    render_pdf: bool = True,
) -> dict:
    """
    Render, detect overflow, and apply compression ladder until one page fits
    or safe minimums are reached.
    """
    work_content = deepcopy(content)
    template = deepcopy(get_template(template_id))

    steps_applied: list[str] = []
    trimmed_log: list[dict] = []

    result, page_count = _render_for_fit(
        work_content, template, template_id, output_path, render_pdf=render_pdf
    )

    if page_count <= 1:
        return _build_result(
            work_content,
            template,
            template_id,
            result,
            page_count,
            steps_applied,
            trimmed_log,
        )

    ladder = [
        _step_reduce_section_spacing,
        _step_reduce_bullet_spacing,
        _step_reduce_margins,
        _step_reduce_line_height,
        _step_reduce_font_size,
        _step_shorten_summary,
        _step_trim_bullet,
        _step_trim_project,
    ]

    for step in ladder:
        applied, note = step(work_content, template, trimmed_log)
        if not applied:
            continue
        if note:
            steps_applied.append(note)
        result, page_count = _render_for_fit(
            work_content, template, template_id, output_path, render_pdf=render_pdf
        )
        if page_count <= 1:
            break

    return _build_result(
        work_content,
        template,
        template_id,
        result,
        page_count,
        steps_applied,
        trimmed_log,
    )


def compress_pdf_to_one_page(pdf_path: str, *, html: Optional[str] = None) -> dict:
    """
    Fallback compression when only HTML+PDF path are available.
    Applies light CSS tightening and re-renders once.
    """
    if not html:
        return {
            "success": False,
            "final_page_count": 0,
            "steps_applied": [],
            "error": "Compression requires HTML context; use fit_resume_to_one_page for full trimming.",
        }

    tightened = _tighten_css(html)
    from services import resume_pdf_renderer

    render = resume_pdf_renderer.render_html_to_pdf(
        tightened, output_path=pdf_path, compress_to_one_page=False
    )
    return {
        "success": bool(render.get("success")),
        "final_page_count": int(render.get("page_count", 1) or 1),
        "steps_applied": ["css_tighten"],
        "trimmed_content_log": [],
    }


def _build_result(
    content: ResumeContent,
    template: dict,
    template_id: str,
    design_result,
    page_count: int,
    steps_applied: list[str],
    trimmed_log: list[dict],
) -> dict:
    fit_passed = page_count <= 1
    layout = "fits_one_page" if fit_passed and not steps_applied else ("compressed" if fit_passed else "overflows")
    return {
        "success": True,
        "fit_passed": fit_passed,
        "compression_steps_applied": steps_applied,
        "final_page_count": page_count,
        "page_count": page_count,
        "trimmed_content_log": trimmed_log,
        "template_id": template_id,
        "final_template": template,
        "layout_status": layout,
        "rendered_pdf_path": getattr(design_result, "rendered_pdf_path", ""),
        "html": getattr(design_result, "html", ""),
        "resume_version_id": getattr(design_result, "resume_version_id", content.resume_version_id),
    }


def _render_for_fit(
    content: ResumeContent,
    template: dict,
    template_id: str,
    output_path: Optional[str],
    *,
    render_pdf: bool = True,
) -> Tuple[object, int]:
    result = design_resume(
        content,
        template_id=template_id,
        render_pdf=render_pdf,
        output_path=output_path,
        template_override=template,
    )
    page_count = int(result.page_count or round(result.estimated_page_count) or 1)
    return result, page_count


def _step_reduce_section_spacing(content: ResumeContent, template: dict, log: list[dict]) -> tuple[bool, str]:
    if template["section_spacing"] <= MIN_TEMPLATE["section_spacing"]:
        return False, ""
    old = template["section_spacing"]
    template["section_spacing"] = max(MIN_TEMPLATE["section_spacing"], old - 2)
    return True, f"reduce_section_spacing:{old}->{template['section_spacing']}"


def _step_reduce_bullet_spacing(content: ResumeContent, template: dict, log: list[dict]) -> tuple[bool, str]:
    if template["bullet_spacing"] <= MIN_TEMPLATE["bullet_spacing"]:
        return False, ""
    old = template["bullet_spacing"]
    template["bullet_spacing"] = max(MIN_TEMPLATE["bullet_spacing"], old - 1)
    return True, f"reduce_bullet_spacing:{old}->{template['bullet_spacing']}"


def _step_reduce_margins(content: ResumeContent, template: dict, log: list[dict]) -> tuple[bool, str]:
    changed = False
    old_top = template["margin_top"]
    old_side = template["margin_side"]
    if template["margin_top"] > MIN_TEMPLATE["margin_top"]:
        template["margin_top"] = max(MIN_TEMPLATE["margin_top"], template["margin_top"] - 2)
        changed = True
    if template["margin_side"] > MIN_TEMPLATE["margin_side"]:
        template["margin_side"] = max(MIN_TEMPLATE["margin_side"], template["margin_side"] - 2)
        changed = True
    if not changed:
        return False, ""
    return True, f"reduce_margins:{old_top}/{old_side}->{template['margin_top']}/{template['margin_side']}"


def _step_reduce_line_height(content: ResumeContent, template: dict, log: list[dict]) -> tuple[bool, str]:
    if template["line_height"] <= MIN_TEMPLATE["line_height"]:
        return False, ""
    old = template["line_height"]
    template["line_height"] = max(MIN_TEMPLATE["line_height"], round(old - 0.05, 2))
    return True, f"reduce_line_height:{old}->{template['line_height']}"


def _step_reduce_font_size(content: ResumeContent, template: dict, log: list[dict]) -> tuple[bool, str]:
    changed = False
    old_body = template["font_size_body"]
    old_head = template["font_size_heading"]
    old_name = template["font_size_name"]

    if template["font_size_body"] > MIN_TEMPLATE["font_size_body"]:
        template["font_size_body"] = max(MIN_TEMPLATE["font_size_body"], round(old_body - 0.3, 2))
        changed = True
    if template["font_size_heading"] > MIN_TEMPLATE["font_size_heading"]:
        template["font_size_heading"] = max(MIN_TEMPLATE["font_size_heading"], round(old_head - 0.3, 2))
        changed = True
    if template["font_size_name"] > MIN_TEMPLATE["font_size_name"]:
        template["font_size_name"] = max(MIN_TEMPLATE["font_size_name"], round(old_name - 0.5, 2))
        changed = True

    if not changed:
        return False, ""
    return True, f"reduce_font_size:{old_body}->{template['font_size_body']}"


def _step_shorten_summary(content: ResumeContent, template: dict, log: list[dict]) -> tuple[bool, str]:
    summary = content.summary or ""
    if len(summary) <= 180:
        return False, ""
    shortened = _shorten_text(summary, 160)
    content.summary = shortened
    log.append({"action": "summary_trim", "original_len": len(summary), "new_len": len(shortened)})
    return True, "shorten_summary"


def _step_trim_bullet(content: ResumeContent, template: dict, log: list[dict]) -> tuple[bool, str]:
    candidate = _find_low_value_bullet(content)
    if not candidate:
        return False, ""
    section, exp_idx, bullet_idx, bullet, score = candidate
    if section == "experience":
        content.work_experiences[exp_idx]["bullets"].pop(bullet_idx)
    else:
        content.projects[exp_idx]["bullets"].pop(bullet_idx)
    log.append({"action": "trim_bullet", "section": section, "removed": bullet, "score": score})
    return True, "trim_bullet"


def _step_trim_project(content: ResumeContent, template: dict, log: list[dict]) -> tuple[bool, str]:
    if len(content.projects) <= 1:
        return False, ""
    idx = _lowest_value_project_index(content.projects)
    removed = content.projects.pop(idx)
    log.append({"action": "trim_project", "removed": removed.get("name", "")})
    return True, "trim_project"


def _find_low_value_bullet(content: ResumeContent):
    candidates = []
    for i, exp in enumerate(content.work_experiences or []):
        bullets = exp.get("bullets") or []
        if len(bullets) <= 1:
            continue
        for j, b in enumerate(bullets):
            score = _bullet_score(b)
            candidates.append(("experience", i, j, b, score))
    for i, proj in enumerate(content.projects or []):
        bullets = proj.get("bullets") or []
        if len(bullets) <= 1:
            continue
        for j, b in enumerate(bullets):
            score = _bullet_score(b) - 0.5  # projects trim slightly earlier
            candidates.append(("projects", i, j, b, score))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[-1])
    return candidates[0]


def _lowest_value_project_index(projects: list[dict]) -> int:
    scored = []
    for idx, proj in enumerate(projects):
        bullets = proj.get("bullets") or []
        if not bullets:
            scored.append((idx, 0.0))
            continue
        avg = sum(_bullet_score(b) for b in bullets) / max(1, len(bullets))
        scored.append((idx, avg))
    scored.sort(key=lambda x: x[1])
    return scored[0][0] if scored else 0


def _bullet_score(text: str) -> float:
    score = 0.0
    if re.search(r"\d", text):
        score += 3.0
    tl = text.lower()
    for v in ACTION_VERBS:
        if v in tl[:60]:
            score += 2.0
            break
    if len(text) >= 90:
        score += 1.0
    return score


def _shorten_text(text: str, max_len: int) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    parts = re.split(r"(?<=[.!?])\s+", text)
    if parts:
        out = parts[0]
        if len(out) <= max_len:
            return out
    return text[:max_len].rstrip() + "..."


def _tighten_css(html: str) -> str:
    html = html or ""
    html = re.sub(r"font-size:\s*([0-9.]+)pt", lambda m: f"font-size: {max(8.5, float(m.group(1)) - 0.5):.1f}pt", html)
    html = re.sub(r"line-height:\s*([0-9.]+)", lambda m: f"line-height: {max(1.15, float(m.group(1)) - 0.1):.2f}", html)
    html = re.sub(r"margin:\s*([0-9.]+)pt\s+([0-9.]+)pt", lambda m: f"margin: {max(10, float(m.group(1)) - 2):.1f}pt {max(10, float(m.group(2)) - 2):.1f}pt", html)
    return html
