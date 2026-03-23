from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from agents.state import AgentState

def tailor_resume(state: AgentState):
    """
    Rewrites the base resume. Naturally incorporates missing skills into 
    the experience and overall summary to boost ATS score while maintaining 
    factual realism. When allowed_skills is provided (truth-safe mode), 
    ONLY add skills from that list—never invent or add unsupported keywords.
    """
    if not state.get("is_eligible", True):
        return {"tailored_resume_text": ""}
        
    llm = ChatOpenAI(model="gpt-4o", temperature=0.7)
    
    missing_skills = state.get("missing_skills", [])
    allowed_skills = state.get("allowed_skills")
    truth_safe_block = ""
    if allowed_skills:
        truth_safe_block = """
8. **TRUTH-SAFE MODE:** You may ONLY weave in skills from this ALLOWED list: {allowed_skills}. 
   Do NOT add any skill, tool, or technology not present in the candidate's master resume. 
   If a JD keyword is not in the allowed list, do NOT add it—this prevents fake claims."""
    
    system_prompt = """You are an elite, $1000/hour executive resume writer specializing in AI & Machine Learning. 
Your goal is to rewrite the candidate's resume so it scores a PERFECT 100 on the ATS for an AI/ML Engineer role.
    
CRITICAL CONSTRAINTS:
1. The candidate is an AI/ML Engineer. Frame their entire persona around Artificial Intelligence, Machine Learning, Data Science, and MLOps.
2. Rewrite experience bullets to subtly and naturally incorporate the MISSING SKILLS, leaning heavily into AI/data engineering contexts.
3. The candidate is an F1 OPT student. Frame their experience highlighting their immediate availability without sponsorship.
4. Do not make up fake companies. Only enhance existing experience with the missing technical keywords contexts.
5. The candidate MUST appear as a local candidate. You MUST change the location in their contact header to perfectly match the TARGET LOCATION.
6. **YOU MUST REWRITE THE PROFESSIONAL SUMMARY** — Do NOT keep the original summary. Write a NEW 2–4 sentence summary that: (a) opens with the TARGET ROLE and TARGET COMPANY, (b) weaves in key skills/requirements from the job description, (c) includes MISSING SKILLS naturally, (d) mentions years of experience and work authorization. The summary must sound tailored to this specific job, not generic.
7. Output the updated resume in a clean Markdown format. Include the rewritten Professional Summary, Skills Section, and Experience section.
{truth_safe_block}

Missing Skills to Weave In: {missing_skills}
Target Role: {target_position} at {target_company}
Target Location: {target_location}
"""
    
    human_prompt = f"""Base Resume:
{state['base_resume_text']}

Job Description Context:
{state['job_description']}

Please provide the fully rewritten resume in Markdown format."""

    if allowed_skills:
        truth_safe_fmt = truth_safe_block.format(allowed_skills=", ".join(str(s) for s in allowed_skills))
    else:
        truth_safe_fmt = ""
    
    messages = [
        SystemMessage(content=system_prompt.format(
            missing_skills=", ".join(missing_skills),
            target_position=state.get('target_position', 'AI/ML Engineer'),
            target_company=state.get('target_company', 'Tech Corp'),
            target_location=state.get('target_location', 'USA'),
            truth_safe_block=truth_safe_fmt,
        )),
        HumanMessage(content=human_prompt)
    ]
    
    response = llm.invoke(messages)
    
    return {
        "tailored_resume_text": response.content
    }
