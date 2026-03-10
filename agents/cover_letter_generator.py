from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from agents.state import AgentState

def generate_cover_letter(state: AgentState):
    """
    Acts as a professional Career Coach to generate a hyper-targeted 
    Cover Letter based on the generated AI/ML resume and the job description.
    """
    if not state.get("is_eligible", True) or not state.get("tailored_resume_text", ""):
        return {"cover_letter_text": ""}
        
    llm = ChatOpenAI(model="gpt-4o", temperature=0.7)
    
    system_prompt = """You are an elite Career Coach specializing in AI & Machine Learning.
Your task is to write a compelling, 1-page Cover Letter for the candidate applying to the Target Role.

CRITICAL 'HUMANIZE' CONSTRAINTS (YOU MUST PASS AI DETECTORS LIKE GPTZERO/AIHUMANIZE):
1. **High Burstiness & Perplexity:** Vary your sentence lengths drastically. Use some very short, punchy sentences. Follow them with longer, complex, compound sentences.
2. **Imperfect Transitions:** Do not use robotic transition words like "Furthermore", "Moreover", "In conclusion", or "Additionally". Use conversational connective tissue.
3. **Show, Don't Tell:** Instead of saying "I am passionate about AI," describe a specific moment or realization from the DXC Technology experience or the custom project that proves it.
4. **Tone:** Confident, slightly conversational but deeply professional. It should sound like it was typed out in a slightly hurried but passionate state by an actual human engineer, not generated.
5. **Formatting:** Output the Cover Letter in clean, readable text format (no markdown headers) with a standard formally addressed block at the top. Keep it under 350 words.
"""
    
    human_prompt = f"""Target Role: {state.get('target_position', 'AI/ML Engineer')}
Target Company: {state.get('target_company', 'Tech Company')}
Candidate Name: {state.get('candidate_name', 'Santhakumar Ramesh')}
Target Location/Address line: {state.get('target_location', 'USA')}

Job Description:
{state['job_description']}

Candidate Final Tailored Resume:
{state['tailored_resume_text']}
"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt)
    ]
    
    response = llm.invoke(messages)
    
    return {
        "cover_letter_text": response.content
    }
