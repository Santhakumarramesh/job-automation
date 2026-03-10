
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
import requests
from bs4 import BeautifulSoup

def get_company_info(company_name: str) -> str:
    """Scrapes Google for a company's 'About Us' page and returns its content."""
    print(f"🕵️‍♀️ Researching company: {company_name}")
    try:
        # Step 1: Google search for the company's about page
        google_url = f"https://www.google.com/search?q={company_name.replace(' ', '+')}+about+us"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(google_url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Step 2: Find the first organic search result link
        about_url = None
        for link in soup.find_all('a'):
            href = link.get('href')
            if href and href.startswith('/url?q='):
                about_url = href.split('/url?q=')[1].split('&')[0]
                if company_name.lower() in about_url:
                    break # Found a likely candidate
        
        if not about_url:
            print("⚠️ Could not find company 'About Us' page.")
            return "Could not automatically retrieve company information."

        # Step 3: Scrape the content from the about page
        response = requests.get(about_url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.content, 'html.parser')
        for script in soup(["script", "style", "nav", "footer"]):
            script.extract()
        
        content = soup.get_text(separator=' ', strip=True)
        print("✅ Company information scraped successfully.")
        return content[:4000] # Limit content to avoid excessive token usage

    except Exception as e:
        print(f"❌ Error scraping company info: {e}")
        return "Could not automatically retrieve company information."


def generate_interview_prep(job_description: str, resume_text: str, company_name: str):
    """Generates a comprehensive interview prep guide using an LLM."""
    print("🧠 Generating AI-powered interview prep guide...")

    llm = ChatOpenAI(model="gpt-4o", temperature=0.5)
    company_info = get_company_info(company_name)

    system_prompt = """You are an elite interview coach. Your task is to create a comprehensive, personalized interview preparation guide based on the provided resume, job description, and company information.

You must generate the guide in a clean, readable markdown format with the following sections:

### Company Dossier
- **About the Company:** [A brief, 2-3 sentence summary of the company based on the scraped info.]
- **Mission & Values:** [Identify and list any stated company mission or values.]
- **Recent News/Talking Points:** [Infer 1-2 potential talking points from the company info.]

###Behavioral Questions (STAR Method)
- **Likely Question 1:** [Generate a likely behavioral question, e.g., 'Tell me about a challenging project.']
- **Your STAR Story:** [Draft a sample STAR (Situation, Task, Action, Result) answer by connecting a specific achievement from the candidate's resume to the question.]
- **Likely Question 2:** [Generate a second likely behavioral question, e.g., 'How do you handle ambiguity?']
- **Your STAR Story:** [Draft another sample STAR answer based on the resume.]

###Technical Questions
- **Core Technology Questions:** [Generate 3-4 likely technical questions based on the core technologies mentioned in the job description (e.g., Python, TensorFlow, AWS).]
- **Role-Specific Scenarios:** [Generate 1-2 scenario-based questions relevant to the role (e.g., 'How would you design a system to...? ').]

###Questions for Them
- **Insightful Questions:** [Suggest 2-3 thoughtful questions the candidate can ask the interviewer about the team, the role, or the company's challenges.]
"""

    human_prompt = f"""**Company Name:** {company_name}

**Scraped Company Information:**
---
{company_info}
---

**Job Description:**
---
{job_description}
---

**Candidate's Resume:**
---
{resume_text}
---

Please generate the interview prep guide in markdown format.
"""

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)]

    try:
        response = llm.invoke(messages)
        print("✅ Interview prep guide generated successfully.")
        return response.content
    except Exception as e:
        print(f"❌ Error generating interview prep guide: {e}")
        return "Failed to generate the interview prep guide. Please try again."
