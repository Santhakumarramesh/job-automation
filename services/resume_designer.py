"""
Phase 4 — One-Page ATS Resume Designer
Generates a clean, ATS-safe one-page HTML resume from a TruthInventory
+ job-tailored content selected by the ATS optimizer.

Three built-in templates:
  classic_ats    — traditional chronological, maximum ATS compatibility
  compact_ats    — tighter spacing, fits more content on one page
  technical_ats  — skills-first layout for engineering roles

Output:
  - rendered HTML (for preview)
  - optional PDF path (via resume_pdf_renderer.py)
  - page_count estimate
  - layout_status (fits_one_page | overflows | compressed)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from services.resume_template_rules import ATS_SAFE_FONT_STACK, TEMPLATE_RULES, get_template

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Resume content dataclass — what the designer works with
# ---------------------------------------------------------------------------

@dataclass
class ResumeContent:
    """Structured content for a single tailored resume."""
    full_name: str = ""
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    github: str = ""
    location: str = ""

    target_title: str = ""          # e.g. "Machine Learning Engineer"
    summary: str = ""               # 2–3 sentence tailored summary

    # Work experience: list of dicts with keys:
    #   title, company, start, end, bullets (list of str)
    work_experiences: list[dict] = field(default_factory=list)

    # Projects: list of dicts with keys:
    #   name, tech_stack, bullets (list of str)
    projects: list[dict] = field(default_factory=list)

    # Education: list of dicts with keys:
    #   degree, school, graduation, gpa (optional)
    education: list[dict] = field(default_factory=list)

    # Skills: dict of category → list of skills
    skills: dict[str, list[str]] = field(default_factory=dict)

    # Metadata
    template_id: str = "classic_ats"
    job_title: str = ""
    company: str = ""
    ats_score: float = 0.0
    resume_version_id: str = ""


@dataclass
class DesignResult:
    html: str = ""
    template_id: str = ""
    estimated_page_count: float = 1.0
    layout_status: str = "fits_one_page"   # fits_one_page | overflows | compressed
    resume_version_id: str = ""
    content_line_count: int = 0
    rendered_pdf_path: str = ""
    page_count: int = 0
    renderer_used: str = ""


TEMPLATES = TEMPLATE_RULES


# ---------------------------------------------------------------------------
# Main designer function
# ---------------------------------------------------------------------------

def design_resume(
    content: ResumeContent,
    template_id: str = "classic_ats",
    *,
    render_pdf: bool = False,
    output_path: Optional[str] = None,
    template_override: Optional[dict] = None,
) -> DesignResult:
    """
    Render a ResumeContent into clean ATS-safe HTML.
    Returns a DesignResult with the HTML and layout metrics.
    """
    template_id = template_id or content.template_id or "classic_ats"
    template = template_override if template_override is not None else get_template(template_id)
    html = _render_template(content, template)

    line_count = html.count("\n")
    page_est = _estimate_page_count(content, template)
    layout_status = "fits_one_page" if page_est <= 1.05 else ("compressed" if page_est <= 1.3 else "overflows")

    result = DesignResult(
        html=html,
        template_id=template_id,
        estimated_page_count=round(page_est, 2),
        layout_status=layout_status,
        resume_version_id=content.resume_version_id,
        content_line_count=line_count,
    )
    if render_pdf:
        from services.resume_pdf_renderer import render_html_to_pdf

        pdf_result = render_html_to_pdf(html, output_path=output_path, compress_to_one_page=False)
        if pdf_result.get("success"):
            result.rendered_pdf_path = pdf_result.get("pdf_path", "")
            result.page_count = int(pdf_result.get("page_count", 1) or 1)
            result.renderer_used = pdf_result.get("renderer_used", "")
            if result.page_count > 1:
                result.layout_status = "overflows"
    return result


def design_resume_from_inventory(
    master_resume_text: str,
    job_title: str,
    company: str,
    job_description: str,
    template_id: str = "classic_ats",
    profile: Optional[dict] = None,
    *,
    resume_text_override: Optional[str] = None,
) -> DesignResult:
    """
    Convenience wrapper — builds ResumeContent from truth inventory + raw resume,
    then renders the template.
    """
    from services.truth_inventory_builder import build_truth_inventory

    content = build_resume_content(
        master_resume_text=master_resume_text,
        job_title=job_title,
        company=company,
        job_description=job_description,
        template_id=template_id,
        profile=profile,
        resume_text_override=resume_text_override,
    )

    return design_resume(content, template_id)


def render_one_page_resume(
    master_resume_text: str,
    job_title: str,
    company: str,
    job_description: str,
    template_id: str = "classic_ats",
    profile: Optional[dict] = None,
    *,
    resume_text_override: Optional[str] = None,
    output_path: Optional[str] = None,
    compress_to_one_page: bool = True,
) -> dict:
    """
    High-level helper: build content, render HTML and PDF, return required outputs.
    """
    content = build_resume_content(
        master_resume_text=master_resume_text,
        job_title=job_title,
        company=company,
        job_description=job_description,
        template_id=template_id,
        profile=profile,
        resume_text_override=resume_text_override,
    )
    if compress_to_one_page:
        from services.resume_page_fit_engine import fit_resume_to_one_page

        return fit_resume_to_one_page(
            content,
            template_id=template_id,
            output_path=output_path,
            render_pdf=True,
        )

    rendered = design_resume(content, template_id=template_id, render_pdf=True, output_path=output_path)
    return {
        "resume_version_id": rendered.resume_version_id,
        "template_id": rendered.template_id,
        "rendered_pdf_path": rendered.rendered_pdf_path,
        "page_count": rendered.page_count or int(round(rendered.estimated_page_count)),
        "layout_status": rendered.layout_status,
        "html": rendered.html,
        "fit_passed": (rendered.page_count or int(round(rendered.estimated_page_count))) <= 1,
        "compression_steps_applied": [],
        "final_page_count": rendered.page_count or int(round(rendered.estimated_page_count)),
        "trimmed_content_log": [],
    }


def build_resume_content(
    master_resume_text: str,
    job_title: str,
    company: str,
    job_description: str,
    template_id: str = "classic_ats",
    profile: Optional[dict] = None,
    *,
    resume_text_override: Optional[str] = None,
) -> ResumeContent:
    from services.truth_inventory_builder import build_truth_inventory
    import uuid

    source_text = resume_text_override or master_resume_text or ""
    inv = build_truth_inventory(
        master_resume_text=master_resume_text or source_text,
        profile=profile,
    )

    content = ResumeContent(
        full_name=inv.full_name,
        email=inv.email,
        phone=inv.phone,
        linkedin=inv.linkedin,
        github=inv.github,
        location=inv.location,
        target_title=job_title or (inv.target_titles[0] if inv.target_titles else ""),
        summary=_extract_summary(source_text) or (inv.summary_text[:500] if inv.summary_text else ""),
        skills=_build_skills_dict(inv.skills_supported, inv.skills_partial),
        template_id=template_id,
        job_title=job_title,
        company=company,
        resume_version_id=str(uuid.uuid4())[:8],
    )

    content.work_experiences = _parse_work_experience(
        _extract_section(source_text, ["experience", "work history", "employment"]) or inv.work_experience_text
    )
    content.projects = _parse_projects(
        _extract_section(source_text, ["projects", "project"]) or inv.projects_text
    )
    content.education = _parse_education(
        _extract_section(source_text, ["education", "academic"]) or inv.education_text
    )
    return content


# ---------------------------------------------------------------------------
# HTML renderers
# ---------------------------------------------------------------------------

def _render_template(content: ResumeContent, template: dict) -> str:
    fs_body = template["font_size_body"]
    fs_h = template["font_size_heading"]
    fs_name = template["font_size_name"]
    lh = template["line_height"]
    mt = template["margin_top"]
    ms = template["margin_side"]
    ss = template["section_spacing"]
    bs = template["bullet_spacing"]
    order = template.get("section_order", ["summary", "experience", "projects", "skills", "education"])

    contact_parts = [p for p in [
        content.email,
        content.phone,
        content.location,
        _link(content.linkedin, "LinkedIn") if content.linkedin else "",
        _link(content.github, "GitHub") if content.github else "",
    ] if p]

    sections_html = ""
    for key in order:
        if key == "summary" and content.summary:
            sections_html += _section("SUMMARY", f'<p style="margin:0">{_esc(content.summary)}</p>', fs_h, ss)
        elif key == "experience" and content.work_experiences:
            exp_html = ""
            for exp in content.work_experiences:
                start = _normalize_date(exp.get("start", ""))
                end = _normalize_date(exp.get("end", "Present")) or "Present"
                bullets_html = "".join(
                    f'<li style="margin-bottom:{bs}pt">{_esc(b)}</li>'
                    for b in exp.get("bullets", [])
                )
                exp_html += f"""
                <div style="margin-bottom:6pt">
                  <div style="display:flex;justify-content:space-between">
                    <strong>{_esc(exp.get("title",""))}</strong>
                    <span style="color:#555">{_esc(start)} – {_esc(end)}</span>
                  </div>
                  <div style="color:#333;margin-bottom:3pt">{_esc(exp.get("company",""))}</div>
                  <ul style="margin:2pt 0 0 14pt;padding:0">{bullets_html}</ul>
                </div>"""
            sections_html += _section("EXPERIENCE", exp_html, fs_h, ss)
        elif key == "projects" and content.projects:
            proj_html = ""
            for proj in content.projects:
                bullets_html = "".join(
                    f'<li style="margin-bottom:{bs}pt">{_esc(b)}</li>'
                    for b in proj.get("bullets", [])
                )
                tech = proj.get("tech_stack", "")
                tech_str = f' <span style="color:#555;font-style:italic">({_esc(tech)})</span>' if tech else ""
                proj_html += f"""
                <div style="margin-bottom:6pt">
                  <strong>{_esc(proj.get("name",""))}</strong>{tech_str}
                  <ul style="margin:2pt 0 0 14pt;padding:0">{bullets_html}</ul>
                </div>"""
            sections_html += _section("PROJECTS", proj_html, fs_h, ss)
        elif key == "skills" and content.skills:
            skill_rows = "".join(
                f'<div><strong>{_esc(cat)}:</strong> {_esc(", ".join(skills))}</div>'
                for cat, skills in content.skills.items()
                if skills
            )
            sections_html += _section("SKILLS", skill_rows, fs_h, ss)
        elif key == "education" and content.education:
            edu_html = ""
            for edu in content.education:
                gpa = f" | GPA: {edu.get('gpa')}" if edu.get("gpa") else ""
                grad = _normalize_date(edu.get("graduation", ""))
                edu_html += f"""
                <div style="margin-bottom:4pt">
                  <div style="display:flex;justify-content:space-between">
                    <strong>{_esc(edu.get("degree",""))}</strong>
                    <span>{_esc(grad)}</span>
                  </div>
                  <div>{_esc(edu.get("school",""))}{_esc(gpa)}</div>
                </div>"""
            sections_html += _section("EDUCATION", edu_html, fs_h, ss)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  * {{ box-sizing: border-box; }}
  body {{
    font-family: {ATS_SAFE_FONT_STACK};
    font-size: {fs_body}pt;
    line-height: {lh};
    margin: {mt}pt {ms}pt;
    color: #1a1a1a;
  }}
  a {{ color: #1a1a1a; text-decoration: none; }}
  ul {{ padding-left: 14pt; }}
  li {{ margin-bottom: {bs}pt; }}
  hr {{ border: none; border-top: 1px solid #333; margin: 4pt 0; }}
</style>
</head>
<body>
  <div style="text-align:center;margin-bottom:8pt">
    <div style="font-size:{fs_name}pt;font-weight:bold">{_esc(content.full_name)}</div>
    {"<div style='font-size:11pt;color:#333;margin-top:2pt'>" + _esc(content.target_title) + "</div>" if content.target_title else ""}
    <div style="font-size:{fs_body}pt;margin-top:4pt">{" | ".join(contact_parts)}</div>
  </div>
  {sections_html}
</body>
</html>"""


# ---------------------------------------------------------------------------
# Section helper
# ---------------------------------------------------------------------------

def _section(heading: str, body_html: str, fs_h: int, ss: int) -> str:
    return f"""
    <div style="margin-bottom:{ss}pt">
      <div style="font-size:{fs_h}pt;font-weight:bold;border-bottom:1px solid #333;padding-bottom:1pt;margin-bottom:4pt;letter-spacing:0.5pt">{heading}</div>
      {body_html}
    </div>"""


def _esc(s) -> str:
    if not s:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _link(url: str, label: str) -> str:
    if not url:
        return ""
    clean = url.replace("https://", "").replace("http://", "").rstrip("/")
    return f'<a href="{_esc(url)}">{_esc(label)}: {_esc(clean)}</a>'


# ---------------------------------------------------------------------------
# Page count estimator
# ---------------------------------------------------------------------------

def _estimate_page_count(content: ResumeContent, template: dict) -> float:
    """
    Rough estimate: count content units and map to page fraction.
    A4 page at 10pt ≈ 55 lines of body text.
    """
    lines = 0
    lines += 3  # header
    if content.summary:
        lines += 3
    for exp in content.work_experiences:
        lines += 2 + len(exp.get("bullets", []))
    for proj in content.projects:
        lines += 2 + len(proj.get("bullets", []))
    if content.skills:
        lines += 1 + len(content.skills)
    for edu in content.education:
        lines += 2

    # Approximate lines per page given font + margins
    lh = template["line_height"]
    fs = template["font_size_body"]
    lines_per_page = (11 - 2 * template["margin_top"] / 72) * (72 / (fs * lh))
    lines_per_page = max(40, min(70, lines_per_page))

    return lines / lines_per_page


# ---------------------------------------------------------------------------
# Content parsers (best-effort from raw text)
# ---------------------------------------------------------------------------

def _parse_work_experience(text: str) -> list[dict]:
    """Parse raw work experience text into structured list."""
    if not text:
        return []

    experiences = []
    current: Optional[dict] = None
    lines = text.split("\n")

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Detect role+company lines (heuristic: contains date patterns)
        date_match = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|20\d\d|present)", line, re.I)
        if date_match and len(line) < 100 and not line.startswith("•") and not line.startswith("-"):
            if current:
                experiences.append(current)
            # Try to extract dates
            start, end = _extract_dates_from_line(line)
            title_part = re.sub(r"\s*[|–\-]\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|20\d\d|Present).*", "", line, flags=re.I).strip()
            current = {"title": title_part, "company": "", "start": start, "end": end, "bullets": []}
        elif current and (line.startswith("•") or line.startswith("-") or line.startswith("*")):
            bullet = re.sub(r"^[•\-\*]\s*", "", line)
            if bullet:
                current["bullets"].append(bullet)
        elif current and not current["company"] and len(line) < 80:
            current["company"] = line

    if current:
        experiences.append(current)

    return experiences[:5]  # cap at 5 roles


def _parse_projects(text: str) -> list[dict]:
    """Parse raw projects text."""
    if not text:
        return []

    projects = []
    current: Optional[dict] = None
    lines = text.split("\n")

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("•") or line.startswith("-") or line.startswith("*"):
            if current:
                bullet = re.sub(r"^[•\-\*]\s*", "", line)
                current["bullets"].append(bullet)
        elif not current or len(line) < 80:
            if current:
                projects.append(current)
            tech_match = re.search(r"\(([^)]+)\)", line)
            tech = tech_match.group(1) if tech_match else ""
            name = re.sub(r"\s*\([^)]+\)", "", line).strip()
            current = {"name": name, "tech_stack": tech, "bullets": []}

    if current:
        projects.append(current)

    return projects[:4]  # cap at 4 projects


def _parse_education(text: str) -> list[dict]:
    """Parse raw education text."""
    if not text:
        return []

    edu_list = []
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    i = 0
    while i < len(lines):
        line = lines[i]
        # Year signal
        year_match = re.search(r"20\d\d|19\d\d", line)
        if year_match or any(kw in line.lower() for kw in ["bachelor", "master", "phd", "b.s", "m.s", "b.e", "m.e"]):
            edu = {
                "degree": line,
                "school": lines[i + 1] if i + 1 < len(lines) else "",
                "graduation": _normalize_date(year_match.group(0) if year_match else ""),
                "gpa": None,
            }
            # Look for GPA
            for j in range(i, min(i + 4, len(lines))):
                gpa_m = re.search(r"gpa[:\s]+(\d\.\d+)", lines[j], re.I)
                if gpa_m:
                    edu["gpa"] = gpa_m.group(1)
            edu_list.append(edu)
        i += 1

    return edu_list[:2]


def _extract_section(text: str, headers: list[str]) -> str:
    if not text:
        return ""
    for name in headers:
        pat = rf"^#+\s*{re.escape(name)}\s*$"
        m = re.search(pat, text, re.M | re.I)
        if m:
            start = m.end()
            next_sec = re.search(r"\n#+\s+", text[start:])
            end = start + next_sec.start() if next_sec else len(text)
            return text[start:end].strip()
        pat_plain = rf"^{re.escape(name)}\s*$"
        m2 = re.search(pat_plain, text, re.M | re.I)
        if m2:
            start = m2.end()
            next_sec = re.search(r"\n[A-Z][A-Z\s]{2,}\n", text[start:])
            end = start + next_sec.start() if next_sec else len(text)
            return text[start:end].strip()
    return ""


def _extract_summary(text: str) -> str:
    summary = _extract_section(text, ["summary", "professional summary", "profile"])
    if summary:
        return summary.replace("\n", " ").strip()[:500]
    # Fallback: first non-empty lines
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    return " ".join(lines[:2])[:500] if lines else ""


def _extract_dates_from_line(line: str) -> tuple[str, str]:
    dates = re.findall(
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*\.?\s*\d{4}|"
        r"\b20\d\d\b|Present|present|current",
        line,
        re.I,
    )
    if not dates:
        # Try numeric formats
        dates = re.findall(r"\b\d{1,2}[/-]\d{4}\b|\b\d{4}[/-]\d{1,2}\b", line)
    start = _normalize_date(dates[0]) if dates else ""
    end = _normalize_date(dates[1]) if len(dates) > 1 else "Present"
    return start, end


def _normalize_date(raw: str) -> str:
    if not raw:
        return ""
    s = str(raw).strip()
    if not s:
        return ""
    low = s.lower()
    if low in ("present", "current", "now"):
        return "Present"

    month_map = {
        "january": "Jan",
        "jan": "Jan",
        "february": "Feb",
        "feb": "Feb",
        "march": "Mar",
        "mar": "Mar",
        "april": "Apr",
        "apr": "Apr",
        "may": "May",
        "june": "Jun",
        "jun": "Jun",
        "july": "Jul",
        "jul": "Jul",
        "august": "Aug",
        "aug": "Aug",
        "september": "Sep",
        "sep": "Sep",
        "sept": "Sep",
        "october": "Oct",
        "oct": "Oct",
        "november": "Nov",
        "nov": "Nov",
        "december": "Dec",
        "dec": "Dec",
    }

    m = re.search(r"\b(20\d{2})\b", s)
    year = m.group(1) if m else ""
    month = ""
    for key, val in month_map.items():
        if re.search(rf"\b{re.escape(key)}\b", low):
            month = val
            break
    if not month:
        # Numeric format: 2021-03 or 03/2021
        m_num = re.search(r"\b(20\d{2})[/-](\d{1,2})\b", s)
        if not m_num:
            m_num = re.search(r"\b(\d{1,2})[/-](20\d{2})\b", s)
        if m_num:
            if len(m_num.groups()) == 2:
                if len(m_num.group(1)) == 4:
                    year = m_num.group(1)
                    mm = int(m_num.group(2))
                else:
                    mm = int(m_num.group(1))
                    year = m_num.group(2)
                months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
                month = months[max(1, min(12, mm)) - 1]
    if month and year:
        return f"{month} {year}"
    return year or s


def _build_skills_dict(supported: list[str], partial: list[str]) -> dict[str, list[str]]:
    """Organize skills into categories for the skills section."""
    categories: dict[str, list[str]] = {
        "Languages": [],
        "ML / AI": [],
        "Frameworks": [],
        "Cloud & DevOps": [],
        "Data & Databases": [],
    }

    ml_ai = {"pytorch", "tensorflow", "scikit-learn", "huggingface", "langchain", "llamaindex",
              "rag", "fine_tuning", "nlp", "computer_vision", "openai"}
    cloud = {"aws", "azure", "gcp", "docker", "kubernetes", "mlflow", "airflow"}
    data = {"sql", "spark", "vector_db", "data_analysis", "a_b_testing"}
    langs = {"python", "typescript", "javascript"}
    frameworks = {"fastapi", "flask", "django", "react"}

    all_skills = set(supported) | set(partial)
    for skill in sorted(all_skills):
        display = skill.replace("_", " ").replace("-", " ").title()
        if skill in langs:
            categories["Languages"].append(display)
        elif skill in ml_ai:
            categories["ML / AI"].append(display)
        elif skill in frameworks:
            categories["Frameworks"].append(display)
        elif skill in cloud:
            categories["Cloud & DevOps"].append(display)
        elif skill in data:
            categories["Data & Databases"].append(display)

    return {k: v for k, v in categories.items() if v}
