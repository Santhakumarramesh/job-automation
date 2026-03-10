
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
        build_styled_resume_pdf(resume_md, resume_filepath, state.get("candidate_name", ""))
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

def build_styled_resume_pdf(markdown_text, filepath, candidate_name):
    doc = SimpleDocTemplate(filepath, pagesize=letter, leftMargin=0.6*inch, rightMargin=0.6*inch, topMargin=0.6*inch, bottomMargin=0.6*inch)
    styles = getSampleStyleSheet()

    # --- Custom Styles based on "Santha Kumar" resume ---
    name_style = ParagraphStyle('Name', parent=styles['h1'], fontName='Helvetica-Bold', fontSize=18, alignment=TA_CENTER, spaceAfter=2)
    contact_style = ParagraphStyle('Contact', parent=styles['Normal'], fontName='Helvetica', fontSize=9, alignment=TA_CENTER, spaceAfter=12)
    section_title_style = ParagraphStyle('SectionTitle', parent=styles['h2'], fontName='Helvetica-Bold', fontSize=11, alignment=TA_LEFT, spaceBefore=8, spaceAfter=4, textColor=colors.darkblue)
    body_style = ParagraphStyle('Body', parent=styles['Normal'], fontName='Helvetica', fontSize=10, leading=12, spaceAfter=2, alignment=TA_LEFT)
    bullet_style = ParagraphStyle('Bullet', parent=body_style, leftIndent=0.25*inch, bulletIndent=0.1*inch)

    Story = []
    
    # Add Name and Contact Info first
    # This part is tricky as we need to extract it from the markdown text
    lines = markdown_text.split('\n')
    name_and_contact = []
    resume_body_lines = []
    header_found = False
    for line in lines:
        if candidate_name in line and not header_found:
             name_and_contact.append(Paragraph(line, name_style))
             header_found = True
        elif header_found and ("EXPERIENCE" not in line.upper() and "SKILLS" not in line.upper() and "EDUCATION" not in line.upper()) and len(line.strip()) > 0:
            name_and_contact.append(Paragraph(line, contact_style))
        else:
            resume_body_lines.append(line)
    
    Story.extend(name_and_contact)
    Story.append(Spacer(1, 0.1*inch))

    for line in resume_body_lines:
        line = line.strip()
        if not line:
            continue
        
        if line.startswith('## '):
            Story.append(Paragraph(line.replace('## ', ''), section_title_style))
            Story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey, spaceAfter=4))
        elif line.isupper() and len(line) < 50:
            Story.append(Paragraph(line, section_title_style))
            Story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey, spaceAfter=4))
        elif line.startswith('-') or line.startswith('*'):
            Story.append(Paragraph(line, style=bullet_style, bulletText='•'))
        else:
            Story.append(Paragraph(line, body_style))
            
    doc.build(Story)

def build_styled_cover_letter_pdf(text, filepath):
    doc = SimpleDocTemplate(filepath, pagesize=letter, leftMargin=1*inch, rightMargin=1*inch, topMargin=1*inch, bottomMargin=1*inch)
    styles = getSampleStyleSheet()
    cl_body_style = ParagraphStyle('CL_Body', parent=styles['Normal'], fontName='Helvetica', fontSize=10.5, leading=14, spaceAfter=12, alignment=TA_LEFT)
    
    Story = []
    for line in text.split('\n'):
        if line.strip():
            Story.append(Paragraph(line, cl_body_style))
            
    doc.build(Story)
