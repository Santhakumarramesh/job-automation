
import os

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from agents.state import AgentState
import json

def extract_skills_llm(text: str, llm: ChatOpenAI):
    """Dynamically extracts skills from a given text using an LLM."""
    system_prompt = """You are an expert resume analyst. Your task is to extract all technical skills, programming languages, frameworks, and methodologies from the provided text.

You must respond in a valid JSON format with a single key, `"skills"`, which contains a list of the extracted skill strings.

Example:
{
    "skills": ["Python", "TensorFlow", "AWS", "Agile", "CI/CD"]
}
"""
    human_prompt = f"Extract the skills from the following text:\n\n---\n{text}"
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)]

    try:
        response = llm.invoke(messages)
        return json.loads(response.content).get("skills", [])
    except Exception as e:
        print(f"Error extracting skills with LLM: {e}")
        return []

def intelligent_project_generator(state: AgentState):
    """Analyzes the skill gap using an LLM and generates a relevant project idea."""
    print("🧠 Performing LLM-powered skill gap analysis...")

    fast = os.getenv("CCP_FAST_PIPELINE", "").strip().lower() in ("1", "true", "yes")
    if fast:
        # Speed mode: skip project generation entirely (cuts multiple LLM calls).
        return {"generated_project_text": ""}

    job_description = state.get('job_description', '')
    resume_text = state.get('base_resume_text', '')
    model = os.getenv("CCP_OPENAI_MODEL") or ("gpt-4o-mini" if fast else "gpt-4o")
    llm = ChatOpenAI(model=model, temperature=0.0)

    # 1. Dynamically extract skills from both texts using the LLM
    jd_skills = set(s.lower() for s in extract_skills_llm(job_description, llm))
    resume_skills = set(s.lower() for s in extract_skills_llm(resume_text, llm))

    # 2. Identify the skill gap
    missing_skills = list(jd_skills - resume_skills)

    if not missing_skills:
        print("✅ No significant skill gaps found by LLM. No project needed.")
        return {"generated_project_text": "After a deep analysis, your skills appear to be a strong match for this role. No new project is necessary."}

    print(f"⚠️ LLM identified skill gaps: {', '.join(missing_skills)}")

    # 3. Use an LLM to generate a relevant project idea
    project_llm = ChatOpenAI(model=model, temperature=0.8)
    system_prompt = """You are a Senior Engineering Manager and Career Mentor for AI/ML professionals.
Your task is to devise a single, high-impact portfolio project that the candidate can build and complete *before* their first interview (realistically within 1-3 days).

CRITICAL CONSTRAINTS:
1.  **Targeted:** The project MUST directly address one or more of the identified 'Missing Skills'.
2.  **Relevant:** The project idea must be a natural extension of the candidate's *existing* skills.
3.  **Scoped for Speed:** This should be a weekend project. Think: a focused script, a fine-tuned model, a small Streamlit/Gradio app, or a data analysis notebook.
4.  **Actionable & Specific:** Provide a clear, one-paragraph project description, a list of key technologies to use, and a suggested project title.
5.  **Format:** Output clean text, not markdown.
"""

    human_prompt = f"""**Candidate's Existing Skills:**
{', '.join(resume_skills)}

**Identified Missing Skills for the Target Role:**
{', '.join(missing_skills[:3])} # Focus on the top 3 gaps

Based on this, generate one specific, fast-to-build project idea.
"""

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)]
    response = project_llm.invoke(messages)
    project_idea = response.content

    print("💡 Generated project idea to address skill gaps.")

    return {"generated_project_text": project_idea}
