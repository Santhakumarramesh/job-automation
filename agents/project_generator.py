from agents.state import AgentState
from services import model_router

def generate_project(state: AgentState):
    """
    If there are missing skills, this agent hallucinates a highly realistic, 
    impressive side-project that perfectly utilizes those skills so they can 
    be added to the resume.
    """
    if not state.get("is_eligible", True) or not state.get("missing_skills", []):
        return {"generated_project_text": ""}
    
    system_prompt = """You are a strategic career advisor. The candidate is an AI/ML Engineer missing several critical skills required by the Job Description.
    
Your task is to invent a highly realistic, impressive AI/ML side-project that the candidate can add to their resume *right now* to bridge this gap. 
The candidate will build this project locally *if* they secure an interview.

CRITICAL CONSTRAINTS:
1. The project must centrally feature these missing skills: {missing_skills}.
2. The project must be an advanced AI, Machine Learning, Deep Learning, or MLOps project (e.g., training a custom LLM, building an RAG pipeline, deploying a predictive model, etc).
3. Provide a Project Title and 3 highly technical, quantifiable bullet points describing the project. Output this in Markdown format.
4. Make it sound extremely professional, suitable for a Senior AI/ML Engineer level.
"""
    
    human_prompt = f"Target Role: {state.get('target_position', 'Engineer')}\nTarget Company: {state.get('target_company', 'Tech Firm')}\nJob Description Context:\n{state['job_description']}"

    out = model_router.generate_text(
        prompt=human_prompt,
        system_prompt=system_prompt.format(
            missing_skills=", ".join(state['missing_skills'])
        ),
        task="reasoning",
        temperature=0.8,
        max_tokens=900,
    )
    generated_text = str(out.get("text") or "").strip()
    if out.get("status") != "ok" or not generated_text:
        generated_text = ""
    
    return {
        "generated_project_text": generated_text
    }
