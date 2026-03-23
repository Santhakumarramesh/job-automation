from typing import TypedDict, List, Optional

class AgentState(TypedDict, total=False):
    # User Inputs
    candidate_name: str
    target_position: str
    target_company: str
    target_location: str
    base_resume_text: str
    job_description: str
    
    # JD Analyzer Outputs
    is_eligible: bool
    eligibility_reason: str
    required_skills: List[str]
    preferred_skills: List[str]
    missing_skills: List[str]
    
    # ATS Scorer Outputs
    initial_ats_score: int
    final_ats_score: int
    feedback: str
    ats_report_path: str
    
    # Job-fit gate (from master_resume_guard)
    job_fit_score: Optional[int]
    fit_decision: str  # Apply | Review | Reject
    unsupported_requirements: List[str]
    
    # Resume Editor Outputs
    tailored_resume_text: str
    humanized_resume_text: str
    generated_project_text: str
    
    # Cover Letter Outputs
    cover_letter_text: str
    humanized_cover_letter_text: str
    
    # File Manager Outputs
    final_pdf_path: str
    cover_letter_pdf_path: str
