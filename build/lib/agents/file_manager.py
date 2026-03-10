
import os
import re
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.units import inch
from reportlab.lib import colors

from agents.state import AgentState

def save_documents(state: AgentState):
    """
    Compiles the final resume and cover letter into styled, ATS-compliant PDFs.
    Uses a clear naming convention: {Name}_{Title}_at_{Company}_{Type}.pdf
    and saves them into a company-specific folder under `generated_resumes`.
    """
    if not state.get("is_eligible", True):
        return {"final_pdf_path": "", "cover_letter_pdf_path": ""}

    # --- Sanitize inputs for filename ---
    name = re.sub(r'[^\w-]', '_', state.get("candidate_name", "Candidate"))
    pos = re.sub(r'[^\w-]', '_', state.get("target_position", "Role"))
    comp = re.sub(r'[^\w-]', '_', state.get("target_company", "Company"))

    base_filename = f"{name}_{pos}_at_{comp}"
    output_dir = os.path.join("generated_resumes", comp)
    os.makedirs(output_dir, exist_ok=True)

    # --- 1. Save the Tailored & Humanized Resume PDF ---
    resume_md = state.get("humanized_resume_text", state.get("tailored_resume_text", ""))
    project_md = state.get("generated_project_text", "")
    if project_md and "No new projects are necessary" not in project_md:
        resume_md += "\n\n## Custom Projects\n" + project_md

    resume_filepath = os.path.join(output_dir, f"{base_filename}_Resume.pdf")
    
    try:
        # Use the new styled PDF builder
        build_styled_resume_pdf(resume_md, resume_filepath, state.get("candidate_name", ""), target_location=state.get("target_location", ""))
        print(f"📄 Resume saved to: {resume_filepath}")
    except Exception as e:
        print(f"❌ Resume PDF Build Error: {e}")
        resume_filepath = "" 

    # --- 2. Save the Humanized Cover Letter PDF ---
    cover_letter_text = state.get("humanized_cover_letter_text", "")
    cl_filepath = ""
    if cover_letter_text:
        cl_filepath = os.path.join(output_dir, f"{base_filename}_Cover_Letter.pdf")
        try:
            build_styled_cover_letter_pdf(cover_letter_text, cl_filepath)
            print(f"✉️ Cover Letter saved to: {cl_filepath}")
        except Exception as e:
            print(f"❌ Cover Letter PDF Build Error: {e}")
            cl_filepath = ""

    return {
        "final_pdf_path": resume_filepath,
        "cover_letter_pdf_path": cl_filepath
    }

def _md_to_reportlab(text):
    """Convert markdown to ReportLab-safe XML (bold, italic)."""
    if not text:
        return ""
    s = str(text)
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    import re
    s = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s)
    s = re.sub(r'\*(.+?)\*', r'<i>\1</i>', s)
    s = re.sub(r'_(.+?)_', r'<i>\1</i>', s)
    return s


def _condense_for_one_page(md_text):
    """Condense STRICTLY for one page: skip Projects, limit to 4 bullets/role, truncate summary, compact skills."""
    lines = md_text.split('\n')
    out = []
    skip_until_next_section = False
    role_bullets = 0
    in_summary = False
    in_skills = False
    skill_lines = []
    SUMMARY_MAX = 250
    for i, line in enumerate(lines):
        s = line.strip()
        if '## Featured Projects' in s or '## Projects' in s or '## Custom Projects' in s:
            skip_until_next_section = True
            continue
        if skip_until_next_section and s.startswith('## '):
            skip_until_next_section = False
        if skip_until_next_section:
            continue
        if s.startswith('## '):
            role_bullets = 0
            if in_skills and skill_lines:
                out.append(' | '.join(skill_lines[:4]))
                skill_lines = []
            in_skills = 'Technical Skills' in s or 'Skills' in s
            in_summary = 'Professional Summary' in s or 'Summary' in s
            if not in_summary:
                summary_chars = 0
        if in_skills and (s.startswith('-') or s.startswith('* ')):
            skill_lines.append(s.lstrip('-* ').strip())
            continue
        if in_skills and s.startswith('## '):
            in_skills = False
        if in_summary and s and not s.startswith('## '):
            if len(s) > SUMMARY_MAX:
                s = s[:SUMMARY_MAX].rsplit(' ', 1)[0] + '...'
                line = s
            in_summary = False
        if s.startswith('-') or s.startswith('* '):
            prev = '\n'.join(lines[max(0,i-15):i])
            if 'Experience' in prev and 'Skills' not in prev and 'Education' not in prev:
                role_bullets += 1
                if role_bullets > 4:
                    continue
        out.append(line)
    if skill_lines:
        out.append(' | '.join(skill_lines[:4]))
    return '\n'.join(out)


def _replace_location_in_contact(header_lines, target_location):
    """Replace location (first segment before |) in contact lines with job location."""
    if not target_location or not header_lines:
        return header_lines
    out = []
    for h in header_lines:
        if ' | ' in h and len(h) < 150 and not h.strip().startswith('#'):
            if re.search(r'@|\+?\d|Email|LinkedIn|GitHub', h, re.I):
                parts = h.split(' | ', 1)
                if len(parts) == 2:
                    out.append(f"{target_location.strip()} | {parts[1]}")
                    continue
        out.append(h)
    return out


def build_styled_resume_pdf(markdown_text, filepath, candidate_name, one_page=True, target_location=""):
    """Build resume PDF. one_page=True: compact layout. target_location overrides contact header location."""
    if one_page:
        markdown_text = _condense_for_one_page(markdown_text)
    doc = SimpleDocTemplate(
        filepath, pagesize=letter,
        leftMargin=0.45*inch, rightMargin=0.45*inch,
        topMargin=0.35*inch, bottomMargin=0.35*inch
    )
    styles = getSampleStyleSheet()

    # STRICT one-page: minimal spacing, compact fonts
    name_style = ParagraphStyle('Name', parent=styles['h1'], fontName='Helvetica-Bold', fontSize=13, alignment=TA_CENTER, spaceAfter=1)
    contact_style = ParagraphStyle('Contact', parent=styles['Normal'], fontName='Helvetica', fontSize=8, alignment=TA_CENTER, spaceAfter=4)
    section_title_style = ParagraphStyle('SectionTitle', parent=styles['h2'], fontName='Helvetica-Bold', fontSize=9, alignment=TA_LEFT, spaceBefore=3, spaceAfter=1, textColor=colors.HexColor('#1a365d'))
    subsection_style = ParagraphStyle('Subsection', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, alignment=TA_LEFT, spaceBefore=2, spaceAfter=0, textColor=colors.HexColor('#1a365d'))
    body_style = ParagraphStyle('Body', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=9, spaceAfter=0, alignment=TA_LEFT, leftIndent=0)
    bullet_style = ParagraphStyle('Bullet', parent=body_style, leftIndent=0.2*inch, bulletIndent=0.08*inch, spaceAfter=0, leading=9)

    Story = []
    lines = markdown_text.split('\n')
    in_header = True
    header_lines = []
    body_lines = []
    pending_subsection = None  # For "Role | Company | Location Date" single-line format

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_header:
                in_header = False
            body_lines.append("")
            continue
        if stripped in ('---', '***', '___'):
            body_lines.append("")
            continue
        if in_header and ("##" not in stripped and "EXPERIENCE" not in stripped.upper() and "SKILLS" not in stripped.upper() and "EDUCATION" not in stripped.upper() and "PROJECTS" not in stripped.upper() and "SUMMARY" not in stripped.upper()):
            first_name = (candidate_name or "").split()[0] or ""
            is_header = (first_name and first_name.upper() in stripped.upper()) or (candidate_name and candidate_name.upper() in stripped.upper()) or (len(header_lines) < 3 and len(stripped) < 120)
            if is_header:
                header_lines.append(stripped)
                continue
        in_header = False
        body_lines.append(stripped)

    header_lines = _replace_location_in_contact(header_lines[:4], target_location)
    first_name = (candidate_name or "").split()[0] or ""
    for h in header_lines:
        if first_name and (first_name.upper() in h.upper() or (candidate_name and candidate_name.upper() in h.upper())):
            Story.append(Paragraph(_md_to_reportlab(h), name_style))
        else:
            Story.append(Paragraph(_md_to_reportlab(h), contact_style))
    Story.append(Spacer(1, 0.04*inch))

    i = 0
    while i < len(body_lines):
        line = body_lines[i]
        if not line.strip():
            i += 1
            continue
        stripped = line.strip()
        if stripped.startswith('## '):
            Story.append(Paragraph(_md_to_reportlab(stripped[3:].strip()), section_title_style))
        elif stripped.startswith('### '):
            role = stripped[4:].strip()
            company_date = ""
            j = i + 1
            while j < len(body_lines):
                nxt = body_lines[j].strip()
                if not nxt or nxt.startswith('-') or nxt.startswith('* '):
                    break
                if nxt.startswith('**') and '|' in nxt:
                    company_date = nxt.replace('**', '').strip()
                    j += 1
                    if j < len(body_lines) and body_lines[j].strip().startswith('*') and not body_lines[j].strip().startswith('**'):
                        company_date += " " + body_lines[j].strip().strip('*').strip()
                        j += 1
                    break
                if nxt.startswith('*') and not nxt.startswith('**') and len(nxt) < 60:
                    company_date = nxt.strip('*').strip()
                    j += 1
                    break
                j += 1
            if company_date:
                Story.append(Paragraph(_md_to_reportlab(f"{role} | {company_date}"), subsection_style))
                i = j
                i -= 1
            else:
                Story.append(Paragraph(_md_to_reportlab(role), subsection_style))
        elif stripped.startswith('- ') or stripped.startswith('* '):
            bullet_text = stripped[2:].strip()
            Story.append(Paragraph(_md_to_reportlab(bullet_text), bullet_style, bulletText='•'))
        elif stripped.startswith('-') or stripped.startswith('*') or stripped.startswith('•'):
            bullet_text = stripped.lstrip('-*• ').strip()
            if bullet_text:
                Story.append(Paragraph(_md_to_reportlab(bullet_text), bullet_style, bulletText='•'))
        elif stripped.startswith('**') and not stripped.startswith('-'):
            if '|' in stripped:
                Story.append(Paragraph(_md_to_reportlab(stripped), subsection_style))
            else:
                edu_school = ""
                edu_date = ""
                skip = 0
                if i + 1 < len(body_lines):
                    n1 = body_lines[i+1].strip()
                    if n1 and not n1.startswith(('##', '-', '*')):
                        edu_school = n1.replace('**', '').replace('*', '').strip()
                        skip = 1
                if i + 2 < len(body_lines):
                    n2 = body_lines[i+2].strip()
                    if n2.startswith('*') and not n2.startswith('**'):
                        edu_date = n2.strip('*').strip()
                        skip = 2
                i += skip
                degree = stripped.replace('**', '').strip()
                combined = f"{degree} | {edu_school} {edu_date}".strip() if edu_school or edu_date else degree
                Story.append(Paragraph(_md_to_reportlab(combined), subsection_style))
        elif stripped.startswith('*') and not stripped.startswith('**') and len(stripped) < 80 and '|' not in stripped:
            pass
        else:
            Story.append(Paragraph(_md_to_reportlab(stripped), body_style))
        i += 1

    doc.build(Story)

def build_styled_cover_letter_pdf(text, filepath):
    doc = SimpleDocTemplate(filepath, pagesize=letter, leftMargin=1*inch, rightMargin=1*inch, topMargin=1*inch, bottomMargin=1*inch)
    styles = getSampleStyleSheet()
    cl_body_style = ParagraphStyle('CL_Body', parent=styles['Normal'], fontName='Helvetica', fontSize=10.5, leading=14, spaceAfter=12, alignment=TA_LEFT)
    Story = []
    for line in text.split('\n'):
        if line.strip():
            Story.append(Paragraph(_md_to_reportlab(line.strip()), cl_body_style))
    doc.build(Story)
