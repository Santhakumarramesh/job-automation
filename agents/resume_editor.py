from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from agents.state import AgentState

def tailor_resume(state: AgentState):
    """
    Rewrites the base resume. Naturally incorporates missing skills into 
    the DXC Technology experience and overall summary to boost ATS score 
    while maintaining factual realism.
    """
    if not state.get("is_eligible", True):
        return {"tailored_resume_text": ""}
        
    llm = ChatOpenAI(model="gpt-4o", temperature=0.7)
    
    system_prompt = """You are an elite, $1000/hour executive resume writer specializing in AI & Machine Learning. 
Your goal is to rewrite the candidate's resume so it scores a PERFECT 100 on the ATS for an AI/ML Engineer role.
    
CRITICAL CONSTRAINTS:
1. The candidate is an AI/ML Engineer. Frame their entire persona around Artificial Intelligence, Machine Learning, Data Science, and MLOps.
2. The candidate previously worked at DXC Technology. You must rewrite their DXC bullets to subtly and naturally incorporate the MISSING SKILLS, leaning heavily into AI/data engineering contexts (e.g., if missing 'AWS', talk about deploying models on AWS at DXC).
3. The candidate is an F1 OPT student. Frame their experience highlighting their immediate availability without sponsorship.
4. Do not make up fake companies. Only enhance existing experience with the missing technical keywords contexts.
5. The candidate MUST appear as a local candidate. You MUST change the location in their contact header to perfectly match the TARGET LOCATION.
6. Output the updated resume in a clean Markdown format. Include a strong Professional Summary, Skills Section, and Experience section.

Missing Skills to Weave In: {missing_skills}
Target Role: {target_position} at {target_company}
Target Location: {target_location}
"""
    
    human_prompt = f"""Base Resume:
{state['base_resume_text']}

Job Description Context:
{state['job_description']}

Please provide the fully rewritten resume in Markdown format."""

    messages = [
        SystemMessage(content=system_prompt.format(
            missing_skills=", ".join(state.get('missing_skills', [])),
            target_position=state.get('target_position', 'AI/ML Engineer'),
            target_company=state.get('target_company', 'Tech Corp'),
            target_location=state.get('target_location', 'USA')
        )),
        HumanMessage(content=human_prompt)
    ]
    
    response = llm.invoke(messages)
    
    return {
        "tailored_resume_text": response.content
    }
