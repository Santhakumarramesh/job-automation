
import streamlit as st
import os
import io
import fitz  # PyMuPDF
from dotenv import load_dotenv
import base64
import zipfile
import csv
import pandas as pd
import requests
from bs4 import BeautifulSoup

from langgraph.graph import StateGraph, END
from agents.state import AgentState
from agents.job_analyzer import analyze_job_description
from agents.resume_editor import tailor_resume
from intelligent_project_generator import intelligent_project_generator
from agents.cover_letter_generator import generate_cover_letter
from agents.job_guard import guard_job_quality
from agents.humanize_resume import humanize_resume
from agents.humanize_cover_letter import humanize_cover_letter
from agents.file_manager import save_documents

from enhanced_job_finder import EnhancedJobFinder
from enhanced_ats_checker import EnhancedATSChecker

# --- Helper Functions ---
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
    with open(file_path, "rb") as f:
        base64_pdf = base64.b64encode(f.read()).decode('utf-8')
    pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800" type="application/pdf"></iframe>'
    st.markdown(pdf_display, unsafe_allow_html=True)

load_dotenv()

st.set_page_config(page_title="Ultimate AI Job Automation Portal", page_icon="🏆", layout="wide")

# --- Main Application State ---
def enhanced_ats_scorer_node(state: AgentState):
    st.write(f"🔬 Running ATS Analysis for {state['target_company']}...")
    checker = EnhancedATSChecker()
    ats_results = checker.comprehensive_ats_check(
        resume_text=state['base_resume_text'],
        job_description=state['job_description'],
        job_title=state['target_position'],
        company_name=state['target_company'],
        location=state['target_location']
    )
    report_filename = f"ATS_Report_{state['target_company']}.xlsx".replace('/', '_')
    ats_report_path = checker.save_ats_results_to_excel(ats_results, filename=report_filename)
    st.write(f"ATS Score for {state['target_company']}: {ats_results['ats_score']}%")
    return {
        "initial_ats_score": ats_results['ats_score'],
        "feedback": "\n".join(ats_results['feedback']),
        "ats_report_path": ats_report_path,
    }

# --- The Complete LangGraph Workflow ---
def build_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("guard_job", guard_job_quality)
    workflow.add_node("analyze_jd", analyze_job_description)
    workflow.add_node("score_resume_enhanced", enhanced_ats_scorer_node)
    workflow.add_node("edit_resume", tailor_resume)
    workflow.add_node("humanize_resume", humanize_resume)
    workflow.add_node("generate_project_intelligent", intelligent_project_generator)
    workflow.add_node("generate_cover_letter", generate_cover_letter)
    workflow.add_node("humanize_cover_letter", humanize_cover_letter)
    workflow.add_node("save_final_documents", save_documents)

    def check_guard(state: AgentState): return "analyze_jd" if state.get("is_eligible", True) else END
    def check_ats_score(state: AgentState): return "generate_project_intelligent" if state.get("initial_ats_score", 0) >= 90 else "edit_resume"

    workflow.add_conditional_edges("guard_job", check_guard, {"analyze_jd": "analyze_jd", END: END})
    workflow.add_edge("analyze_jd", "score_resume_enhanced")
    workflow.add_conditional_edges("score_resume_enhanced", check_ats_score, {"generate_project_intelligent": "generate_project_intelligent", "edit_resume": "edit_resume"})
    workflow.add_edge("edit_resume", "humanize_resume")
    workflow.add_edge("humanize_resume", "score_resume_enhanced")
    workflow.add_edge("generate_project_intelligent", "generate_cover_letter")
    workflow.add_edge("generate_cover_letter", "humanize_cover_letter")
    workflow.add_edge("humanize_cover_letter", "save_final_documents")
    workflow.add_edge("save_final_documents", END)
    workflow.set_entry_point("guard_job")
    return workflow.compile()

graph = build_graph()

def extract_text_from_pdf(pdf_bytes): 
    return "".join(page.get_text() for page in fitz.open(stream=pdf_bytes, filetype="pdf"))

# --- Streamlit UI ---
st.title("🏆 Ultimate AI Job Automation Portal")
st.markdown("Apify Job Finder | Humanized Resumes & Cover Letters | Advanced ATS Scoring | Intelligent Project Suggestions")

st.sidebar.header("🔑 API Configuration")
openai_api_key = st.sidebar.text_input("OpenAI API Key", type="password", value=os.getenv("OPENAI_API_KEY", ""))
apify_api_key = st.sidebar.text_input("Apify API Key", type="password", value=os.getenv("APIFY_API_KEY", ""))
if not all([openai_api_key, apify_api_key]):
    st.sidebar.error("Please provide all required API keys to proceed.")
else:
    os.environ["OPENAI_API_KEY"] = openai_api_key
    os.environ["APIFY_API_KEY"] = apify_api_key

st.sidebar.markdown("---")
st.sidebar.subheader("👤 Candidate Information")
candidate_name = st.sidebar.text_input("Your Name", value="Santhakumar Ramesh")
target_position = st.sidebar.text_input("Target Role", value="AI/ML Engineer")
base_resume = st.sidebar.file_uploader("Upload Your Base Resume (PDF)", type=["pdf"])
if base_resume: st.session_state.base_resume_bytes = base_resume.read()

# --- TABS ---
tab1, tab2, tab3 = st.tabs(["📄 Single Job Application", "🚀 Batch URL Processor", "🤖 AI Job Finder (Apify)"])

with tab1:
    st.header("Single Job Generation")
    target_company = st.text_input("Target Company Name")
    target_location = st.text_input("Target Job Location (e.g., San Francisco, CA or Remote)")
    jd_text = st.text_area("Paste Job Description Here", height=250)

    if st.button("Run Full Automation Pipeline", type="primary", key="single_job_button"):
        if not all([st.session_state.get("base_resume_bytes"), jd_text, target_company, target_location]):
            st.error("Please fill in all fields and upload your resume.")
        else:
            with st.spinner("Running the full multi-agent automation pipeline..."):
                try:
                    initial_state = {
                        "candidate_name": candidate_name, "target_position": target_position, "target_company": target_company,
                        "target_location": target_location, "base_resume_text": extract_text_from_pdf(st.session_state.base_resume_bytes), "job_description": jd_text,
                    }
                    final_state = graph.invoke(initial_state)
                    st.success("Pipeline Complete!")
                    
                    st.metric("Final ATS Score", f"{final_state.get('initial_ats_score', 0)}%")
                    with st.expander("💡 Suggested Project to Fill Skill Gaps"):
                        st.markdown(final_state.get("generated_project_text", "No project suggestion."))
                    
                    col1, col2, col3 = st.columns(3)
                    if final_state.get("final_pdf_path"): col1.download_button("📄 Download Humanized Resume", open(final_state["final_pdf_path"], "rb").read(), os.path.basename(final_state["final_pdf_path"]), "application/pdf", use_container_width=True)
                    if final_state.get("cover_letter_pdf_path"): col2.download_button("✉️ Download Humanized Cover Letter", open(final_state["cover_letter_pdf_path"], "rb").read(), os.path.basename(final_state["cover_letter_pdf_path"]), "application/pdf", use_container_width=True)
                    if final_state.get("ats_report_path"): col3.download_button("📊 Download ATS Report (Excel)", open(final_state["ats_report_path"], "rb").read(), os.path.basename(final_state["ats_report_path"]), "application/vnd.ms-excel", use_container_width=True)

                    if final_state.get("final_pdf_path"): display_pdf(final_state["final_pdf_path"])

                except Exception as e: st.error(f"An error occurred: {e}")

with tab2:
    st.header("🚀 Batch URL Processor")
    st.markdown("Paste job URLs (one per line). The system will scrape each job description and run the full automation pipeline.")

    urls_input = st.text_area("Paste Job URLs Here", height=200, key="batch_urls")

    if st.button("Run Batch URL Processing", type="primary", key="batch_process_button"):
        if not all([st.session_state.get("base_resume_bytes"), urls_input]):
            st.error("Please upload your resume and paste at least one URL.")
        else:
            urls = [u.strip() for u in urls_input.split('\n') if u.strip()]
            st.info(f"Found {len(urls)} URLs to process. This may take some time...")

            all_generated_files = []
            for i, url in enumerate(urls):
                with st.expander(f"Processing URL {i+1}: {url}", expanded=True):
                    try:
                        st.write("Scraping job description...")
                        jd = scrape_job_url(url)
                        if jd.startswith("Error:"):
                            st.error(f"Could not scrape job description: {jd}")
                            continue

                        # Simple guess for company name from URL
                        try:
                            domain_parts = url.split('//')[1].split('/')[0].split('.')
                            company_name = (domain_parts[-2] if len(domain_parts) > 1 else domain_parts[0]).capitalize()
                        except Exception:
                            company_name = f"Company_from_URL_{i+1}"

                        st.write(f"Running pipeline for {company_name}...")
                        initial_state = {
                            "candidate_name": candidate_name,
                            "target_position": target_position, # Using general role from sidebar
                            "target_company": company_name,
                            "target_location": "Remote", # Location is hard to guess from URL
                            "base_resume_text": extract_text_from_pdf(st.session_state.base_resume_bytes),
                            "job_description": jd,
                        }
                        final_state = graph.invoke(initial_state)
                        st.success(f"Successfully processed URL! Final ATS Score: {final_state.get('initial_ats_score', 'N/A')}% ")

                        # Add files to the list for zipping
                        if final_state.get("final_pdf_path"): all_generated_files.append(final_state["final_pdf_path"])
                        if final_state.get("cover_letter_pdf_path"): all_generated_files.append(final_state["cover_letter_pdf_path"])
                        if final_state.get("ats_report_path"): all_generated_files.append(final_state["ats_report_path"])

                    except Exception as e:
                        st.error(f"Failed to process URL {url}: {e}")

            if all_generated_files:
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w") as zip_f:
                    for file_path in all_generated_files:
                        zip_f.write(file_path, os.path.basename(file_path))
                
                st.download_button(
                    label="📥 Download All Generated Files (ZIP)",
                    data=zip_buffer.getvalue(),
                    file_name="batch_generated_documents.zip",
                    mime="application/zip",
                    use_container_width=True
                )

with tab3:
    st.header("🤖 AI Job Finder (Apify)")
    max_jobs = st.slider("Max jobs to find", 10, 200, 50)
    if st.button("Find Jobs with Apify", type="primary"):
        if not apify_api_key:
            st.error("Please enter your Apify API Key in the sidebar to use this feature.")
        elif not st.session_state.get("base_resume_bytes"): 
            st.error("Upload resume first.")
        else:
            with st.spinner("Finding jobs..."):
                finder = EnhancedJobFinder(apify_api_key)
                jobs_df = finder.find_jobs_with_apify(extract_text_from_pdf(st.session_state.base_resume_bytes), max_jobs)
                if not jobs_df.empty:
                    st.success(f"Found {len(jobs_df)} jobs!")
                    jobs_df["Select"] = False

                    # FIX: Ensure all required columns exist before displaying
                    required_cols = ['title', 'company', 'location', 'resume_match_score', 'description']
                    for col in required_cols:
                        if col not in jobs_df.columns:
                            jobs_df[col] = "Not Available" # Add missing columns with a placeholder

                    st.session_state.jobs_df = jobs_df

    if 'jobs_df' in st.session_state:
        edited_df = st.data_editor(
            st.session_state.jobs_df[["Select", 'title', 'company', 'location', 'resume_match_score']],
            column_config={
                "Select": st.column_config.CheckboxColumn(
                    "Select",
                    default=False,
                )
            },
            disabled=['title', 'company', 'location', 'resume_match_score'],
            hide_index=True,
        )
        st.session_state.jobs_df["Select"] = edited_df["Select"]

        if st.button("🌟 Generate Documents for Selected Jobs (Premium)", type="primary"):
            selected_jobs = st.session_state.jobs_df[st.session_state.jobs_df["Select"]]
            if selected_jobs.empty:
                st.warning("Please select at least one job to generate documents.")
            else:
                st.info(f"Found {len(selected_jobs)} jobs to process. This may take a few minutes...")
                
                all_generated_files = []
                for index, job in selected_jobs.iterrows():
                    with st.expander(f"Processing: {job['title']} at {job['company']}", expanded=True):
                        try:
                            initial_state = {
                                "candidate_name": candidate_name,
                                "target_position": job['title'],
                                "target_company": job['company'],
                                "target_location": job['location'],
                                "base_resume_text": extract_text_from_pdf(st.session_state.base_resume_bytes),
                                "job_description": job['description'],
                            }
                            final_state = graph.invoke(initial_state)
                            st.success("Successfully generated documents!")

                            col1, col2 = st.columns(2)
                            if final_state.get("final_pdf_path"): 
                                col1.download_button("📄 Resume", open(final_state["final_pdf_path"], "rb").read(), os.path.basename(final_state["final_pdf_path"]), "application/pdf")
                                all_generated_files.append(final_state["final_pdf_path"])
                            if final_state.get("cover_letter_pdf_path"): 
                                col2.download_button("✉️ Cover Letter", open(final_state["cover_letter_pdf_path"], "rb").read(), os.path.basename(final_state["cover_letter_pdf_path"]), "application/pdf")
                                all_generated_files.append(final_state["cover_letter_pdf_path"])

                        except Exception as e:
                            st.error(f"Failed to process job: {e}")

                if all_generated_files:
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w") as zip_f:
                        for file_path in all_generated_files:
                            zip_f.write(file_path, os.path.basename(file_path))
                    
                    st.download_button(
                        "📥 Download All Generated Files (ZIP)",
                        zip_buffer.getvalue(),
                        "generated_documents.zip",
                        "application/zip",
                        use_container_width=True
                    )
