import os

from agents.state import AgentState
from services import model_router

def analyze_job_description(state: AgentState):
    """
    Parses the Job Description, extracts required skills, and rigorously checks 
    sponsorship and citizenship requirements for F1 OPT compatibility.
    """
    fast = os.getenv("CCP_FAST_PIPELINE", "").strip().lower() in ("1", "true", "yes")
    
    system_prompt = """You are an expert technical recruiter analyzing a job description. 
You must extract the core requirements and meticulously check for citizenship / sponsorship constraints.
The candidate is on an F1 OPT student visa. This means they CAN work immediately without sponsorship, 
but they CANNOT apply for roles requiring US Citizenship or active Security Clearances.

Extract the following information in strict JSON format:
{
    "is_eligible": true/false, // Set to false ONLY if explicitly "US Citizen ONLY" or "Security Clearance Required". Set to true if "No Sponsorship" or silent.
    "eligibility_reason": "Explanation of eligibility",
    "required_skills": ["skill1", "skill2"],
    "preferred_skills": ["skill3", "skill4"]
}
"""
    
    human_prompt = f"Here is the Job Description:\n{state['job_description']}"
    out = model_router.generate_json(
        prompt=human_prompt,
        system_prompt=system_prompt,
        task="fast" if fast else "reasoning",
        temperature=0.0,
        max_tokens=500,
        required_keys=("is_eligible", "eligibility_reason", "required_skills", "preferred_skills"),
    )
    result = out.get("data", {}) if out.get("status") == "ok" else {}
    if not isinstance(result, dict):
        result = {}
    if not result:
        # Keep pipeline moving; manual policy gates later still apply.
        return {
            "is_eligible": True,
            "eligibility_reason": "LLM job analysis unavailable; routed to supervised review.",
            "required_skills": [],
            "preferred_skills": [],
        }
    
    return {
        "is_eligible": result.get("is_eligible", False),
        "eligibility_reason": result.get("eligibility_reason", ""),
        "required_skills": result.get("required_skills", []),
        "preferred_skills": result.get("preferred_skills", [])
    }
