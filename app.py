import streamlit as st
import os
import io
import fitz  # PyMuPDF
from dotenv import load_dotenv

from langgraph.graph import StateGraph, END
from agents.state import AgentState
from agents.job_analyzer import analyze_job_description
from agents.ats_scorer import score_resume
from agents.resume_editor import tailor_resume
from agents.project_generator import generate_project
from agents.cover_letter_generator import generate_cover_letter
from agents.job_guard import guard_job_quality
from agents.file_manager import save_resume

import requests
from bs4 import BeautifulSoup
import base64
import zipfile
import csv

def scrape_job_url(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        for script in soup(["script", "style", "nav", "footer"]):
            script.extract()
        return soup.get_text(separator=' ', strip=True)
    except Exception as e:
        return f"Error: {e}"

def display_pdf(file_path):
    """Embeds a local PDF into the Streamlit dashboard using an iframe."""
    with open(file_path, "rb") as f:
        base64_pdf = base64.b64encode(f.read()).decode('utf-8')
    pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800" type="application/pdf"></iframe>'
    st.markdown(pdf_display, unsafe_allow_html=True)


load_dotenv()

st.set_page_config(page_title="AI Resume Tailor (F1 OPT Friendly)", page_icon="📄", layout="wide")

# --- LangGraph Setup ---
def build_graph():
    workflow = StateGraph(AgentState)
    
    workflow.add_node("guard_job", guard_job_quality)
    workflow.add_node("analyze_jd", analyze_job_description)
    workflow.add_node("score_resume", score_resume)
    workflow.add_node("edit_resume", tailor_resume)
    workflow.add_node("generate_project", generate_project)
    workflow.add_node("generate_cover_letter", generate_cover_letter)
    workflow.add_node("save_file", save_resume)
    
    # Define conditional edges
    def check_guard(state: AgentState):
        if not state.get("is_eligible", True):
            return "end"
        return "analyze_jd"
        
    def check_ats_score(state: AgentState):
        if not state.get("is_eligible", True):
            return "end"
        if state.get("initial_ats_score", 0) >= 100:
            return "generate_project"
        return "edit_resume"
        
    workflow.add_conditional_edges(
        "guard_job",
        check_guard,
        {
            "analyze_jd": "analyze_jd",
            "end": END
        }
    )
        
    workflow.add_edge("analyze_jd", "score_resume")
    
    workflow.add_conditional_edges(
        "score_resume",
        check_ats_score,
        {
            "generate_project": "generate_project",
            "edit_resume": "edit_resume",
            "end": END
        }
    )
    
    # After editing, it must be re-scored to ensure it hit 100%
    workflow.add_edge("edit_resume", "score_resume")
    
    workflow.add_edge("generate_project", "generate_cover_letter")
    workflow.add_edge("generate_cover_letter", "save_file")
    workflow.add_edge("save_file", END)
    
    workflow.set_entry_point("guard_job")
    return workflow.compile()

graph = build_graph()

# --- PDF Extraction Helper ---
def extract_text_from_pdf(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text()
    return text

# --- Streamlit UI ---
st.title("AI Resume Tailor & ATS Scorer (F1 OPT Optimized)")
st.markdown("Optimize your resume for a 100% ATS score based on Job Descriptions. Automatically handles F1 OPT & DXC Technology Experience integration, and generates missing skill side-projects.")

st.sidebar.header("Configuration")
openai_api_key = st.sidebar.text_input("OpenAI API Key", type="password", value=os.getenv("OPENAI_API_KEY", ""))

if not openai_api_key:
    st.sidebar.warning("Please enter your OpenAI API key to proceed.")
else:
    os.environ["OPENAI_API_KEY"] = openai_api_key

# Initialize Session State for Memory
if "base_resume_bytes" not in st.session_state:
    st.session_state.base_resume_bytes = None

st.sidebar.markdown("---")
st.sidebar.subheader("Candidate Information")
candidate_name = st.sidebar.text_input("Name", value="Santhakumar Ramesh")
target_position = st.sidebar.text_input("Target Position", value="AI/ML Engineer")
target_company = st.sidebar.text_input("Target Company (if single job)", value="")
target_location = st.sidebar.text_input("Target Location", value="USA")

base_resume = st.sidebar.file_uploader("Upload Base Resume (PDF)", type=["pdf"])
if base_resume:
    st.session_state.base_resume_bytes = base_resume.read()

tab1, tab2 = st.tabs(["📄 Single Job Application", "🚀 Batch URL Processor (Auto-Apply Prep)"])

with tab1:
    st.header("Single Job Generation")
    jd_text = st.text_area("Paste Job Description Here", height=300)

    if st.button("Analyze & Tailor Resume", type="primary"):
        if not openai_api_key:
            st.error("Missing OpenAI API Key.")
        elif not (st.session_state.base_resume_bytes and jd_text and candidate_name and target_position):
            st.error("Please fill in all details and upload your base resume pdf.")
        else:
            with st.spinner("Extracting PDF text..."):
                extracted_resume_text = extract_text_from_pdf(st.session_state.base_resume_bytes)
                
            st.info("Starting Multi-Agent Resume Pipeline...")
            
            initial_state = {
                "candidate_name": candidate_name,
                "target_position": target_position,
                "target_company": target_company,
                "target_location": target_location,
                "base_resume_text": extracted_resume_text,
                "job_description": jd_text,
            }
        
        # Run Graph
        with st.spinner("Agents are analyzing capabilities and editing the resume..."):
            try:
                final_state = graph.invoke(initial_state)
                
                # Check Citizenship Status
                if not final_state.get("is_eligible", True):
                    st.error(f"⚠️ Eligibility Warning: {final_state.get('eligibility_reason')}")
                    st.warning("Skipped Tailoring: This role requires US Citizenship or Security Clearance. F1 OPT is not eligible.")
                else:
                    st.success("Analysis Complete!")
                    st.metric("Initial ATS Score", f"{final_state.get('initial_ats_score', 0)}%")
                    
                    st.subheader("ATS Feedback")
                    st.write(final_state.get("feedback", ""))
                    
                    with st.expander("View Generated Project Idea"):
                        st.markdown(final_state.get("generated_project_text", "No specific projects needed."))
                        
                    with st.expander("View Tailored Resume Text"):
                        st.markdown(final_state.get("tailored_resume_text", ""))
                        
                    with st.expander("View Cover Letter Text"):
                        st.text(final_state.get("cover_letter_text", ""))
                        
                    # File Downloads
                    col_dl1, col_dl2 = st.columns(2)
                    
                    pdf_path = final_state.get("final_pdf_path", "")
                    if pdf_path and os.path.exists(pdf_path):
                        with col_dl1:
                            with open(pdf_path, "rb") as pdf_file:
                                st.download_button(
                                    label="📄 Download 100% ATS Resume (PDF)",
                                    data=pdf_file,
                                    file_name=os.path.basename(pdf_path),
                                    mime="application/pdf",
                                    use_container_width=True
                                )
                                
                    cl_pdf_path = final_state.get("cover_letter_pdf_path", "")
                    if cl_pdf_path and os.path.exists(cl_pdf_path):
                        with col_dl2:
                            with open(cl_pdf_path, "rb") as cl_pdf_file:
                                st.download_button(
                                    label="✉️ Download Tailored Cover Letter (PDF)",
                                    data=cl_pdf_file,
                                    file_name=os.path.basename(cl_pdf_path),
                                    mime="application/pdf",
                                    use_container_width=True
                                )
                                
                    st.divider()
                    st.subheader("Final PDF Preview")
                    if pdf_path and os.path.exists(pdf_path):
                         display_pdf(pdf_path)
                            
            except Exception as e:
                st.error(f"An error occurred during pipeline execution: {e}")

with tab2:
    st.header("Batch Process Jobs from URLs")
    st.markdown("Paste a list of Job URLs (Greenhouse, Lever, Workday, etc.). The agent will scrape the job descriptions and batch-generate all tailored resumes and cover letters directly into the `generated_resumes` folder on your desktop.")
    
    urls_input = st.text_area("Paste Job URLs (One per line)", height=200)
    
    if st.button("Start Batch Processing", type="primary"):
        if not openai_api_key:
            st.error("Missing API Key.")
        elif not base_resume:
            st.error("Please upload your Base Resume in the sidebar.")
        elif not urls_input.strip():
            st.error("Please provide at least one URL.")
        else:
            urls = [u.strip() for u in urls_input.split('\n') if u.strip()]
            extracted_resume_text = extract_text_from_pdf(st.session_state.base_resume_bytes)
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            generated_files = []
            tracker_data = []
            
            for i, url in enumerate(urls):
                status_text.text(f"Scraping Job {i+1} of {len(urls)}: {url}")
                scraped_jd = scrape_job_url(url)
                guessed_company = url.split("://")[1].split("/")[0].replace("www.", "").split(".")[0].capitalize()
                
                with st.expander(f"Execution Log: {guessed_company}", expanded=True):
                    log_container = st.empty()
                    
                    initial_state = {
                        "candidate_name": candidate_name,
                        "target_position": target_position,
                        "target_company": guessed_company,
                        "target_location": target_location,
                        "base_resume_text": extracted_resume_text,
                        "job_description": scraped_jd,
                    }
                    
                    try:
                        log_container.code("Job Guard Analysis Started...\nInitializing AI Agents...\nAnalyzing Job Description & Target Skills...", language="bash")
                        
                        final_state = graph.invoke(initial_state)
                        
                        if not final_state.get("is_eligible", True):
                            log_container.code("Result: FAILED -> Shielded by Job Guard / Or Visa Sponsorship Required", language="bash")
                            st.warning(f"Skipped {guessed_company}: Not an eligible role (Job Guard/Citizenship).")
                            tracker_data.append([guessed_company, target_position, url, "Skipped by Guard / Citizenship Required", "", ""])
                        else:
                            final_score = final_state.get('initial_ats_score', 100)
                            log_container.code(f"Resume Tailored.\nATS Iteration Complete.\nFinal Simulated ATS Score: {final_score}%\nProjects Generated.\nCover Letter Drafted.\nFiles Saved Successfully.", language="bash")
                            st.success(f"Generated ATS Resume & Cover Letter for {guessed_company}!")
                            
                            res_path = final_state.get("final_pdf_path", "")
                            cov_path = final_state.get("cover_letter_pdf_path", "")
                            
                            if res_path:
                                 generated_files.append(res_path)
                            if cov_path:
                                 generated_files.append(cov_path)
                                 
                            tracker_data.append([guessed_company, target_position, url, f"{final_score}% ATS", res_path, cov_path])
                                 
                    except Exception as e:
                        log_container.code(f"CRITICAL ERROR: {e}", language="bash")
                        st.error(f"Failed to process {url}: {e}")
                        tracker_data.append([guessed_company, target_position, url, f"Error: {e}", "", ""])
                    
                progress_bar.progress((i + 1) / len(urls))
                
            status_text.text("Batch Processing Complete!")
            st.balloons()
            
            # --- Generate Master CSV Tracker ---
            if tracker_data:
                tracker_csv_path = os.path.join("generated_resumes", "Job_Applications_Tracker.csv")
                os.makedirs("generated_resumes", exist_ok=True)
                with open(tracker_csv_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["Company Name", "Target Role", "Job Post URL", "Status / ATS Score", "Resume File Path", "Cover Letter File Path"])
                    writer.writerows(tracker_data)
                generated_files.append(tracker_csv_path)
            
            if generated_files:
                # Create ZIP File in memory
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    for file_path in generated_files:
                        if os.path.exists(file_path):
                            zip_file.write(file_path, os.path.basename(file_path))
                
                st.download_button(
                    label="🗂️ Download All Generated Files (ZIP)",
                    data=zip_buffer.getvalue(),
                    file_name="Automated_Job_Applications.zip",
                    mime="application/zip",
                    type="primary",
                    use_container_width=True
                )
            else:
                st.warning("No files were generated (all roles may have required US Citizenship).")
