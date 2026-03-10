import json
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from agents.state import AgentState

def analyze_job_description(state: AgentState):
    """
    Parses the Job Description, extracts required skills, and rigorously checks 
    sponsorship and citizenship requirements for F1 OPT compatibility.
    """
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    
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
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt)
    ]
    
    # Use LLM with JSON format constraints
    response = llm.invoke(messages, response_format={"type": "json_object"})
    result = json.loads(response.content)
    
    return {
        "is_eligible": result.get("is_eligible", False),
        "eligibility_reason": result.get("eligibility_reason", ""),
        "required_skills": result.get("required_skills", []),
        "preferred_skills": result.get("preferred_skills", [])
    }
