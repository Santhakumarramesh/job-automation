
import os

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from agents.state import AgentState

def humanize_resume(state: AgentState):
    """
    Humanizes the tailored resume text using a sophisticated prompt with GPT-4o.
    This avoids the need for a separate, paid humanizer service.
    """
    print("🤖 Self-humanizing resume text with GPT-4o...")
    
    fast = os.getenv("CCP_FAST_PIPELINE", "").strip().lower() in ("1", "true", "yes")
    resume_text = state.get("tailored_resume_text", "")
    if fast:
        # Speed mode: do not run LLM humanization.
        return {"humanized_resume_text": resume_text}

    model = os.getenv("CCP_OPENAI_MODEL") or ("gpt-4o-mini" if fast else "gpt-4o")
    llm = ChatOpenAI(model=model, temperature=0.7)
    
    if not resume_text or len(resume_text) < 100:
        print("⚠️ Resume text is too short to humanize. Skipping.")
        return {"humanized_resume_text": resume_text}

    system_prompt = """You are an expert editor tasked with rewriting AI-generated text to be indistinguishable from human writing.
    Your goal is to pass AI detection tools by increasing the text's perplexity and burstiness.

    CRITICAL INSTRUCTIONS:
    1.  **Vary Sentence Structure:** Mix short, direct sentences with longer, more complex or compound sentences.
    2.  **Avoid AI Buzzwords:** Replace common AI-generated phrases (e.g., "leveraging synergies," "passionate and results-oriented") with more grounded, natural language.
    3.  **Introduce Nuance:** Do not just list skills. Frame them within the context of achievements. Show, don't just tell.
    4.  **Maintain Professionalism:** The tone must remain highly professional and suitable for a resume.
    5.  **PRESERVE THE PROFESSIONAL SUMMARY:** The Professional Summary has been tailored to a specific job. Do NOT change its meaning, company/role mentions, or key keywords. Only improve phrasing for natural flow. Keep the summary intact.
    6.  **Output ONLY the rewritten text.** Do not add any commentary before or after.
    """

    human_prompt = f"Please rewrite the following resume text to make it sound as if it were written by a human expert. Increase the perplexity and burstiness of the language while retaining all key information and professional tone. IMPORTANT: Preserve the Professional Summary content (company, role, keywords) — only refine its phrasing:\n\n---\n\n{resume_text}"

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)]
    
    try:
        response = llm.invoke(messages)
        humanized_text = response.content
        print("✅ Resume text has been successfully self-humanized.")
        return {"humanized_resume_text": humanized_text}
    except Exception as e:
        print(f"❌ Error during self-humanization: {e}. Returning original text.")
        return {"humanized_resume_text": resume_text}
