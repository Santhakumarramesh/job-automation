from agents.state import AgentState
from services import model_router

def score_resume(state: AgentState):
    """
    Acts as an Applicant Tracking System (ATS). Compares the base resume against 
    the Job Description to calculate a match score and identify missing keywords.
    """
    # If not eligible (e.g., requires US Citizen), skip scoring
    if not state.get("is_eligible", True):
        return {
            "initial_ats_score": 0,
            "feedback": "Not eligible due to citizenship/sponsorship requirements.",
            "missing_skills": []
        }
        
    system_prompt = """You are an aggressive Applicant Tracking System (ATS). 
You will compare the provided Resume text against the required and preferred skills 
from the Job Description.

Be strict. Calculate an ATS percentage score (0-100). Identify exactly which required 
and preferred skills from the JD are completely missing from the resume.

Return the result in this exact JSON format:
{
    "ats_score": 65,
    "missing_skills": ["Kafka", "GraphQL"],
    "feedback": "The resume lacks backend streaming technologies required."
}
"""
    
    # During loop, score the tailored resume if it exists, otherwise base resume
    resume_to_score = state.get('tailored_resume_text') or state['base_resume_text']
    
    human_prompt = f"""Job Description Skills REQUIRED: {state.get('required_skills', [])}
Job Description Skills PREFERRED: {state.get('preferred_skills', [])}

Candidate Resume:
{resume_to_score}
"""
    out = model_router.generate_json(
        prompt=human_prompt,
        system_prompt=system_prompt,
        task="reasoning",
        temperature=0.0,
        max_tokens=420,
        required_keys=("ats_score", "missing_skills", "feedback"),
    )
    result = out.get("data", {}) if out.get("status") == "ok" else {}
    if not isinstance(result, dict):
        result = {}
    if not result:
        return {
            "initial_ats_score": 0,
            "missing_skills": [],
            "feedback": "ATS scoring unavailable; manual review required.",
        }
    
    return {
        "initial_ats_score": result.get("ats_score", 0),
        "missing_skills": result.get("missing_skills", []),
        "feedback": result.get("feedback", "")
    }
