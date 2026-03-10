
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from agents.state import AgentState
import re

def intelligent_project_generator(state: AgentState):
    """
    Analyzes the skill gap between the resume and job description, then generates
    a relevant, completable project idea to fill that gap.
    """
    job_description = state.get('job_description', '')
    resume_text = state.get('base_resume_text', '')

    # 1. Extract skills from both the job description and the resume
    jd_skills = set(extract_skills(job_description))
    resume_skills = set(extract_skills(resume_text))

    # 2. Identify the skill gap
    missing_skills = list(jd_skills - resume_skills)

    if not missing_skills:
        print("✅ No significant skill gaps found. No project generation needed.")
        return {"generated_project_text": "No new projects are necessary for this role. Your skills are a strong match."}

    print(f"⚠️ Skill gaps identified: {', '.join(missing_skills)}")

    # 3. Use an LLM to generate a relevant project idea
    llm = ChatOpenAI(model="gpt-4o", temperature=0.8)

    system_prompt = """You are a Senior Engineering Manager and Career Mentor for AI/ML professionals.
Your task is to devise a single, high-impact portfolio project that the candidate can build and complete *before* their first interview (realistically within 1-3 days).

CRITICAL CONSTRAINTS:
1.  **Targeted:** The project MUST directly address one or more of the identified 'Missing Skills'.
2.  **Relevant:** The project idea must be based on the candidate's *existing* skills. It should be a natural extension of their expertise, not something completely new.
3.  **Scoped for Speed:** This is not a multi-week project. It should be something that can be realistically built and pushed to GitHub in a weekend. Think: a focused script, a fine-tuned model, a small Streamlit/Gradio app, or a data analysis notebook.
4.  **Actionable & Specific:** Provide a clear, one-paragraph project description. Include a list of key technologies to use and a suggested project title.
5.  **Format:** Output should be clean text, not markdown.
"""

    human_prompt = f"""**Candidate's Existing Skills:**
{', '.join(resume_skills)}

**Identified Missing Skills for the Target Role:**
{', '.join(missing_skills[:3])} # Focus on the top 3 gaps

**Candidate's Resume (for context):**
{resume_text}

**Job Description (for context):**
{job_description}

Based on this, generate one specific, fast-to-build project idea.
"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt)
    ]

    response = llm.invoke(messages)
    project_idea = response.content

    print(f"💡 Generated project idea to address skill gaps.")

    return {
        "generated_project_text": project_idea
    }

def extract_skills(text):
    """A simple regex-based skill extractor."""
    text = text.lower()
    # This list should be expanded for more accuracy
    known_skills = [
        'python', 'java', 'c++', 'javascript', 'typescript', 'go', 'rust', 'scala', 'kotlin',
        'tensorflow', 'pytorch', 'keras', 'scikit-learn', 'pandas', 'numpy', 'matplotlib', 'seaborn',
        'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'terraform', 'ansible',
        'sql', 'nosql', 'mongodb', 'postgresql', 'mysql', 'redis', 'cassandra',
        'spark', 'hadoop', 'kafka', 'flink',
        'react', 'angular', 'vue', 'node.js',
        'deep learning', 'machine learning', 'natural language processing', 'nlp', 'computer vision',
        'agile', 'scrum', 'ci/cd'
    ]
    
    found_skills = []
    for skill in known_skills:
        # Use word boundaries to avoid matching substrings (e.g., 'go' in 'golang')
        if re.search(r'\b' + re.escape(skill) + r'\b', text):
            found_skills.append(skill)
            
    return list(set(found_skills))
