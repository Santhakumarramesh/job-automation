from typing import TypedDict, List

class AgentState(TypedDict):
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
    
    # Resume Editor Outputs
    tailored_resume_text: str
    generated_project_text: str
    
    # Cover Letter Outputs
    cover_letter_text: str
    
    # File Manager Outputs
    final_pdf_path: str
    cover_letter_pdf_path: str
