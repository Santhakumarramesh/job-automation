import os
import markdown
import re
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.units import inch

from agents.state import AgentState

def save_resume(state: AgentState):
    """
    Compiles the tailored resume and project into a single 1-page ATS-compliant PDF 
    using ReportLab (strict fonts, no weird columns, machine-readable).
    """
    if not state.get("is_eligible", True):
        return {"final_pdf_path": ""}

    final_md = state.get("tailored_resume_text", "")
    project_md = state.get("generated_project_text", "")
    
    if project_md:
        final_md += "\n\n## Custom Projects\n" + project_md

    # Strip markdown syntax for ATS text processing (very basic parsing for MVP)
    # In a fully robust system, use a proper Markdown -> Platypus Flowable converter.
    clean_text = final_md.replace('*', '').replace('# ', '').replace('## ', '')
    lines = clean_text.split('\n')

    name = state.get("candidate_name", "Candidate").replace(" ", "_")
    pos = state.get("target_position", "Role").replace(" ", "_")
    comp = state.get("target_company", "Company").replace(" ", "_")
    loc = state.get("target_location", "Location").replace(" ", "_")
    
    filename = f"{name}_{pos}_{comp}_{loc}.pdf"
    output_dir = os.path.join("generated_resumes", comp)
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)

    # Setup ReportLab Document (Very tight margins to ensure 1-page fit)
    doc = SimpleDocTemplate(
        filepath, 
        pagesize=letter,
        rightMargin=0.5*inch, leftMargin=0.5*inch,
        topMargin=0.5*inch, bottomMargin=0.5*inch
    )

    styles = getSampleStyleSheet()
    
    # Define ATS-Friendly Styles
    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,  # Small font to fit on 1 page
        leading=11,  # Tight leading
        spaceAfter=3,
        alignment=TA_LEFT
    )
    
    header_style = ParagraphStyle(
        'Header',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=11,
        spaceAfter=2,
        spaceBefore=6,
        alignment=TA_LEFT
    )

    Story = []
    
    for line in lines:
        if not line.strip():
            continue
            
        if line.isupper() and len(line) < 30: # Heuristic for section headers
             Story.append(Paragraph(line, header_style))
             Story.append(HRFlowable(width="100%", thickness=1, color="black", spaceBefore=1, spaceAfter=2))
        else:
             Story.append(Paragraph(line, body_style))
        
    try:
        doc.build(Story)
    except Exception as e:
        print(f"PDF Build Error: {e}")
        
    # --- Generate Cover Letter PDF ---
    cover_letter_text = state.get("cover_letter_text", "")
    cl_filepath = ""
    
    if cover_letter_text:
        cl_filename = f"{name}_{pos}_{comp}_{loc}_Cover_Letter.pdf"
        cl_filepath = os.path.join(output_dir, cl_filename)
        
        cl_doc = SimpleDocTemplate(
            cl_filepath, 
            pagesize=letter,
            rightMargin=1*inch, leftMargin=1*inch,
            topMargin=1*inch, bottomMargin=1*inch
        )
        
        cl_Story = []
        cl_body_style = ParagraphStyle(
            'CL_Body',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=11,
            leading=14,
            spaceAfter=10,
            alignment=TA_LEFT
        )
        
        for line in cover_letter_text.split('\n'):
            if line.strip():
                cl_Story.append(Paragraph(line.replace('*', ''), cl_body_style))
                
        try:
            cl_doc.build(cl_Story)
        except Exception as e:
            print(f"Cover Letter PDF Build Error: {e}")

    return {
        "final_pdf_path": filepath,
        "cover_letter_pdf_path": cl_filepath
    }
