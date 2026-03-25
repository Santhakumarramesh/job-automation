
import os

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from agents.state import AgentState
from agents.interview_prep_agent import get_company_info  # Re-using the company scraper

def generate_cover_letter(state: AgentState):
    """
    Generates a targeted Cover Letter, subtly matching the company's tone,
    and then runs it through a self-humanization prompt.
    """
    print("✍️ Generating cover letter with tone matching...")
    
    if not state.get("is_eligible", True) or not state.get("tailored_resume_text", ""):
        return {"cover_letter_text": ""}
        
    fast = os.getenv("CCP_FAST_PIPELINE", "").strip().lower() in ("1", "true", "yes")
    model = os.getenv("CCP_OPENAI_MODEL") or ("gpt-4o-mini" if fast else "gpt-4o")
    llm = ChatOpenAI(model=model, temperature=0.7)
    
    # --- Tone Matching --- #
    company_name = state.get("target_company", "")
    tone_prompt = ""

    if not fast:
        company_info = get_company_info(company_name)
        if "Could not automatically retrieve" not in company_info:
            tone_prompt = f"""First, analyze the following 'About Us' text to understand the company's culture and brand voice (e.g., formal and corporate vs. playful and startup-y).

**Company Info for Tone Analysis:**
---
{company_info}
---

Now, generate the cover letter, subtly adapting its tone to match the company's voice.
"""
    # --- End Tone Matching --- #

    system_prompt = f"""You are an elite Career Coach specializing in AI & Machine Learning.
Your task is to write a compelling, 1-page Cover Letter for the candidate applying to the Target Role.

{tone_prompt}

CRITICAL 'HUMANIZE' CONSTRAINTS:
1. **High Burstiness & Perplexity:** Vary your sentence lengths drastically. Use some very short, punchy sentences, followed by longer, more complex ones.
2. **Imperfect Transitions:** Do not use robotic transition words like "Furthermore" or "Additionally." Use conversational connective tissue.
3. **Show, Don't Tell:** Instead of saying "I am passionate about AI," describe a specific moment or realization that proves it.
4. **Tone:** Confident, slightly conversational but deeply professional. The tone should be influenced by the company info provided.
5. **Formatting:** Output clean, readable text. Keep it under 350 words.
"""
    
    human_prompt = f"""Target Role: {state.get('target_position', 'AI/ML Engineer')}
Target Company: {company_name}
Candidate Name: {state.get('candidate_name', 'Santhakumar Ramesh')}
Target Location/Address line: {state.get('target_location', 'USA')}

**Candidate's Final Tailored Resume:**
{state['tailored_resume_text']}

**Job Description:**
{state['job_description']}
"""

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)]
    
    try:
        response = llm.invoke(messages)
        ai_generated_text = response.content
        print("✅ Cover letter generated successfully with tone matching.")
        # The self-humanization is now part of the main generation prompt
        return {"cover_letter_text": ai_generated_text}
    except Exception as e:
        print(f"❌ Error during cover letter generation: {e}")
        return {"cover_letter_text": "Failed to generate cover letter."}
