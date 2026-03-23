
import streamlit as st
import json
import os
import pathlib
import pandas as pd
from dotenv import load_dotenv

# PDF extraction - try PyMuPDF (fitz) first, fallback to pypdf
try:
    import fitz  # PyMuPDF
    def _extract_pdf(pdf_bytes):
        return "".join(page.get_text() for page in fitz.open(stream=pdf_bytes, filetype="pdf"))
except ImportError:
    try:
        from pypdf import PdfReader
        def _extract_pdf(pdf_bytes):
            import io
            return "".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf_bytes)).pages)
    except ImportError:
        def _extract_pdf(pdf_bytes):
            raise ImportError(
                "PDF support required. Run: pip install pymupdf  (or: pip install pypdf)\n"
                "If using venv: source venv/bin/activate && pip install pymupdf"
            )
import base64
import io
import zipfile
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

# Import the new, upgraded modules
from enhanced_job_finder import EnhancedJobFinder
from enhanced_ats_checker import EnhancedATSChecker
from agents.iterative_ats_optimizer import run_iterative_ats_optimizer
from agents.master_resume_guard import parse_master_resume, compute_job_fit_score
import application_tracker
from application_tracker import log_application, load_applications
from interview_prep_agent import generate_interview_prep

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

def _extract_location_from_jd(jd_text):
    """Extract job location from job description text. Returns empty string if not found."""
    import re
    if not jd_text or jd_text.startswith("Error:"):
        return ""
    text = jd_text[:3000]
    for pat in [
        r'Location[:\s]+([^\n|]+?)(?:\n|$)',
        r'Work Location[:\s]+([^\n|]+?)(?:\n|$)',
        r'Based in[:\s]+([^\n|]+?)(?:\n|$)',
        r'Office Location[:\s]+([^\n|]+?)(?:\n|$)',
        r'Job Location[:\s]+([^\n|]+?)(?:\n|$)',
    ]:
        m = re.search(pat, text, re.I)
        if m:
            loc = m.group(1).strip()
            if len(loc) < 80:
                return loc
    if re.search(r'\bRemote\b', text, re.I):
        return "Remote"
    return ""

def display_pdf(file_path):
    with open(file_path, "rb") as f:
        base64_pdf = base64.b64encode(f.read()).decode('utf-8')
    pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800" type="application/pdf"></iframe>'
    st.markdown(pdf_display, unsafe_allow_html=True)

load_dotenv()
st.set_page_config(page_title="Career Co-Pilot Pro", page_icon="🚀", layout="wide")

# Credentials file - save here so you don't re-enter each time
CREDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
def _load_saved_creds():
    """Load API keys from .env (supports APIFY_API_TOKEN or APIFY_API_KEY)."""
    load_dotenv(CREDS_FILE)
    return {
        "openai": os.getenv("OPENAI_API_KEY", ""),
        "apify": os.getenv("APIFY_API_KEY") or os.getenv("APIFY_API_TOKEN", ""),
        "name": os.getenv("CANDIDATE_NAME", "Santhakumar Ramesh"),
    }
def _save_creds(openai_key: str, apify_key: str, name: str):
    """Save credentials to .env for next session. Preserves other keys."""
    skip_prefixes = ("OPENAI_API_KEY=", "APIFY_API_KEY=", "APIFY_API_TOKEN=", "CANDIDATE_NAME=")
    lines = []
    if os.path.isfile(CREDS_FILE):
        with open(CREDS_FILE, "r") as f:
            for line in f:
                if not any(line.strip().startswith(p) for p in skip_prefixes):
                    lines.append(line.rstrip())
    with open(CREDS_FILE, "w") as f:
        if openai_key:
            f.write(f"OPENAI_API_KEY={openai_key}\n")
        if apify_key:
            f.write(f"APIFY_API_TOKEN={apify_key}\n")
        if name:
            f.write(f"CANDIDATE_NAME={name}\n")
        for line in lines:
            if line:
                f.write(line + "\n")

# --- Main Application State & Graph ---
def enhanced_ats_scorer_node(state: AgentState):
    st.write(f"🔬 Running Semantic ATS Analysis for {state['target_company']}...")
    checker = EnhancedATSChecker()
    master_text = state.get("base_resume_text", "")
    ats_results = checker.comprehensive_ats_check(
        resume_text=state['base_resume_text'],
        job_description=state['job_description'],
        job_title=state['target_position'],
        company_name=state['target_company'],
        location=state['target_location'],
        target_score=100,
        master_resume_text=master_text,
    )
    report_filename = f"ATS_Report_{state['target_company']}.xlsx".replace('/', '_')
    ats_report_path = checker.save_ats_results_to_excel(ats_results, filename=report_filename)
    st.write(f"Semantic ATS Score for {state['target_company']}: {ats_results['ats_score']}%")
    missing = ats_results.get("detailed_breakdown", {}).get("missing_keywords", [])
    return {
        "initial_ats_score": ats_results['ats_score'],
        "feedback": "\n".join(ats_results['feedback']) if isinstance(ats_results['feedback'], list) else ats_results['feedback'],
        "ats_report_path": ats_report_path,
        "missing_skills": missing,
    }


def iterative_ats_optimizer_node(state: AgentState):
    """Iterative loop until ATS=100 or no truthful improvement. Truth-safe mode."""
    st.write(f"🔄 Running iterative ATS optimizer (target 100, truth-safe) for {state['target_company']}...")
    checker = EnhancedATSChecker()
    opt_result = run_iterative_ats_optimizer(
        state=state,
        ats_checker=checker,
        tailor_fn=tailor_resume,
        humanize_fn=humanize_resume,
        target_score=100,
        max_attempts=5,
        truth_safe=True,
    )
    # Compute job-fit
    master_inv = parse_master_resume(state.get("base_resume_text", ""))
    fit = compute_job_fit_score(
        state.get("job_description", ""),
        master_inv,
        ats_score=opt_result.get("final_ats_score", 0),
    )
    ats_results = checker.comprehensive_ats_check(
        resume_text=opt_result["humanized_resume_text"],
        job_description=state.get("job_description", ""),
        job_title=state.get("target_position", ""),
        company_name=state.get("target_company", ""),
        location=state.get("target_location", ""),
        target_score=100,
        master_resume_text=state.get("base_resume_text", ""),
    )
    report_filename = f"ATS_Report_{state['target_company']}.xlsx".replace('/', '_')
    ats_report_path = checker.save_ats_results_to_excel(ats_results, filename=report_filename)

    st.write(f"✅ Iterative ATS complete after {opt_result.get('attempts', 0)} attempts. Score: {opt_result['final_ats_score']}%")
    fit_decision = "Apply" if fit.get("apply") else ("Reject" if fit.get("reject") else "Review")
    return {
        "tailored_resume_text": opt_result["tailored_resume_text"],
        "humanized_resume_text": opt_result["humanized_resume_text"],
        "initial_ats_score": opt_result["final_ats_score"],
        "final_ats_score": opt_result["final_ats_score"],
        "feedback": "\n".join(opt_result.get("feedback", [])) if isinstance(opt_result.get("feedback"), list) else str(opt_result.get("feedback", "")),
        "ats_report_path": ats_report_path,
        "job_fit_score": fit.get("score"),
        "fit_decision": fit_decision,
        "unsupported_requirements": fit.get("unsupported_requirements", []),
    }


def build_graph(use_iterative_ats: bool = False):
    workflow = StateGraph(AgentState)
    workflow.add_node("guard_job", guard_job_quality)
    workflow.add_node("analyze_jd", analyze_job_description)
    workflow.add_node("score_resume_enhanced", enhanced_ats_scorer_node)
    workflow.add_node("iterative_ats", iterative_ats_optimizer_node)
    workflow.add_node("edit_resume", tailor_resume)
    workflow.add_node("humanize_resume", humanize_resume)
    workflow.add_node("generate_project_intelligent", intelligent_project_generator)
    workflow.add_node("generate_cover_letter", generate_cover_letter)
    workflow.add_node("humanize_cover_letter", humanize_cover_letter)
    workflow.add_node("save_final_documents", save_documents)
    workflow.add_node("log_application_node", log_application)

    def check_guard(state: AgentState): return "analyze_jd" if state.get("is_eligible", True) else END
    def check_ats_score(state: AgentState): return "generate_project_intelligent" if state.get("initial_ats_score", 0) >= 75 else "edit_resume"

    workflow.set_entry_point("guard_job")
    workflow.add_conditional_edges("guard_job", check_guard, {"analyze_jd": "analyze_jd", END: END})
    if use_iterative_ats:
        workflow.add_edge("analyze_jd", "iterative_ats")
        workflow.add_edge("iterative_ats", "generate_project_intelligent")
    else:
        workflow.add_edge("analyze_jd", "score_resume_enhanced")
        workflow.add_conditional_edges("score_resume_enhanced", check_ats_score, {"generate_project_intelligent": "generate_project_intelligent", "edit_resume": "edit_resume"})
        workflow.add_edge("edit_resume", "humanize_resume")
        workflow.add_edge("humanize_resume", "generate_project_intelligent")
    workflow.add_edge("generate_project_intelligent", "generate_cover_letter")
    workflow.add_edge("generate_cover_letter", "humanize_cover_letter")
    workflow.add_edge("humanize_cover_letter", "save_final_documents")
    workflow.add_edge("save_final_documents", "log_application_node")
    workflow.add_edge("log_application_node", END)
    return workflow.compile()

def extract_text_from_pdf(pdf_bytes):
    if pdf_bytes is None:
        return ""
    return _extract_pdf(pdf_bytes)

# --- Streamlit UI ---
st.title("🚀 Career Co-Pilot Pro")
st.markdown("LLM-Powered Job Finding, Semantic Analysis, and Interview Preparation")

saved = _load_saved_creds()
st.sidebar.header("🔑 API Configuration")
openai_api_key = st.sidebar.text_input("OpenAI API Key", type="password", value=saved["openai"], key="openai_key")
apify_api_key = st.sidebar.text_input("Apify API Key", type="password", value=saved["apify"], key="apify_key")

st.sidebar.markdown("---")
st.sidebar.subheader("👤 Candidate Information")
candidate_name = st.sidebar.text_input("Your Name", value=saved["name"], key="candidate_name")

# Master_Resumes folder: quick-select from saved PDFs
MASTER_RESUMES_DIR = pathlib.Path(__file__).resolve().parent / "Master_Resumes"
master_pdfs = list(MASTER_RESUMES_DIR.glob("*.pdf")) if MASTER_RESUMES_DIR.exists() else []
if master_pdfs:
    master_choice = st.sidebar.selectbox("Or pick from Master_Resumes", ["— Upload below —"] + [p.name for p in master_pdfs])
    if master_choice != "— Upload below —":
        sel_path = MASTER_RESUMES_DIR / master_choice
        if sel_path.exists():
            st.session_state.base_resume_bytes = sel_path.read_bytes()

base_resume = st.sidebar.file_uploader("Upload Your Base Resume (PDF)", type=["pdf"])
if base_resume: st.session_state.base_resume_bytes = base_resume.read()

if st.sidebar.button("💾 Save credentials (no re-enter next time)", use_container_width=True):
    _save_creds(openai_api_key, apify_api_key, candidate_name)
    st.sidebar.success("Saved to .env – reload the page to confirm.")

use_iterative_ats = st.sidebar.checkbox(
    "Use iterative ATS (target 100, truth-safe)",
    value=True,
    help="Loop until internal ATS score = 100, using only skills from master resume. Auto-apply only when job is a full fit.",
)

st.sidebar.markdown("---")
if not all([openai_api_key, apify_api_key]):
    st.error("Please provide all required API keys in the sidebar to activate the portal.")
    st.stop()

os.environ["OPENAI_API_KEY"] = openai_api_key
os.environ["APIFY_API_KEY"] = apify_api_key

graph = build_graph(use_iterative_ats=use_iterative_ats)

# --- TABS ---
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📄 Single Job", "🚀 Batch URL Processor", "🤖 AI Job Finder", "🎯 Live ATS Optimizer", "💼 My Applications"])

with tab1:
    st.header("Single Job Application")
    target_company = st.text_input("Target Company Name")
    target_location = st.text_input("Target Job Location (e.g., San Francisco, CA or Remote)")
    target_position = st.text_input("Target Role", value="AI/ML Engineer")
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
                    
                    st.metric("Final Semantic ATS Score", f"{final_state.get('initial_ats_score', final_state.get('final_ats_score', 0))}%")
                    if final_state.get("fit_decision"):
                        st.metric("Fit Decision", final_state["fit_decision"])
                    if final_state.get("unsupported_requirements"):
                        with st.expander("⚠️ Unsupported JD requirements (not added)"):
                            st.write(", ".join(final_state["unsupported_requirements"]))
                    with st.expander("💡 Suggested Project to Fill Skill Gaps"):
                        st.markdown(final_state.get("generated_project_text", "No project suggestion."))
                    
                    col1, col2, col3 = st.columns(3)
                    if final_state.get("final_pdf_path") and os.path.isfile(final_state["final_pdf_path"]):
                        with open(final_state["final_pdf_path"], "rb") as f:
                            col1.download_button("📄 Download Humanized Resume", f.read(), os.path.basename(final_state["final_pdf_path"]), "application/pdf", use_container_width=True)
                    if final_state.get("cover_letter_pdf_path") and os.path.isfile(final_state["cover_letter_pdf_path"]):
                        with open(final_state["cover_letter_pdf_path"], "rb") as f:
                            col2.download_button("✉️ Download Humanized Cover Letter", f.read(), os.path.basename(final_state["cover_letter_pdf_path"]), "application/pdf", use_container_width=True)
                    if final_state.get("ats_report_path") and os.path.isfile(final_state["ats_report_path"]):
                        with open(final_state["ats_report_path"], "rb") as f:
                            col3.download_button("📊 Download ATS Report (Excel)", f.read(), os.path.basename(final_state["ats_report_path"]), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
                    if final_state.get("final_pdf_path") and os.path.isfile(final_state["final_pdf_path"]):
                        display_pdf(final_state["final_pdf_path"])

                except Exception as e: st.error(f"An error occurred: {e}")

with tab2:
    st.header("🚀 Batch Process Jobs from URLs")
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

                        try:
                            company_name_from_url = url.split(".")[0].split("//")[1].capitalize()
                        except:
                            company_name_from_url = f"Company_{i+1}"

                        loc = _extract_location_from_jd(jd) or "USA"
                        st.write(f"Running pipeline for {company_name_from_url}...")
                        initial_state = {
                            "candidate_name": candidate_name,
                            "target_position": "AI/ML Engineer",
                            "target_company": company_name_from_url,
                            "target_location": loc,
                            "base_resume_text": extract_text_from_pdf(st.session_state.base_resume_bytes),
                            "job_description": jd,
                        }
                        final_state = graph.invoke(initial_state)
                        st.success(f"Successfully generated documents for {company_name_from_url}!")
                        all_generated_files.extend([final_state.get('final_pdf_path'), final_state.get('cover_letter_pdf_path')])
                    except Exception as e:
                        st.error(f"Failed to process URL {url}: {e}")
            
            if all_generated_files:
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w") as zip_f:
                    for file_path in filter(None, all_generated_files):
                        if file_path and os.path.isfile(file_path):
                            zip_f.write(file_path, os.path.basename(file_path))
                st.download_button("📥 Download All Batch Files (ZIP)", zip_buffer.getvalue(), "batch_documents.zip", "application/zip", use_container_width=True)

with tab3:
    st.header("🤖 AI Job Finder")
    job_source = st.selectbox(
        "Job source",
        ["Apify", "LinkedIn MCP", "Both"],
        help="Apify: AI Deep Job Search. LinkedIn MCP: requires linkedin-mcp-server running (see providers/linkedin_mcp_jobs.py).",
    )
    provider_map = {"Apify": "apify", "LinkedIn MCP": "linkedin_mcp", "Both": "both"}
    provider = provider_map[job_source]
    max_jobs = st.slider("Max jobs to find", 10, 200, 50)
    needs_apify = provider in ("apify", "both")
    if needs_apify and not apify_api_key:
        st.warning("Apify API key required for this source.")
    btn_disabled = (needs_apify and not apify_api_key)
    if st.button("Find Jobs", type="primary", disabled=btn_disabled):
        if not st.session_state.get("base_resume_bytes"): 
            st.error("Upload resume first.")
        else:
            with st.spinner(f"Finding jobs via {job_source}..."):
                finder = EnhancedJobFinder(apify_api_key or "", provider=provider)
                jobs_df = finder.find_jobs_with_apify(extract_text_from_pdf(st.session_state.base_resume_bytes), max_jobs)
                if not jobs_df.empty:
                    st.success(f"Found {len(jobs_df)} jobs!")
                    required_cols = ['title', 'company', 'location', 'description']
                    for col in required_cols:
                        if col not in jobs_df.columns:
                            jobs_df[col] = "Not Available"
                    st.session_state.jobs_df = jobs_df

    if 'jobs_df' in st.session_state:
        df = st.session_state.jobs_df
        # Normalize Apify column names (different actors return different keys)
        col_map = {'position': 'title', 'jobTitle': 'title', 'companyName': 'company', 'company_name': 'company'}
        for old, new in col_map.items():
            if old in df.columns and new not in df.columns:
                df[new] = df[old]
        if 'Select' not in df.columns:
            df['Select'] = False
        for col in ['title', 'company', 'location', 'description']:
            if col not in df.columns:
                df[col] = "Not Available"
        st.session_state.jobs_df = df

        # Define the columns to display and configure them
        column_config = {
            "Select": st.column_config.CheckboxColumn("Select", default=False),
            "title": st.column_config.LinkColumn("Job Title", display_text="Apply ↗", width="medium"),
            "company": "Company",
            "location": "Location",
            "description_snippet": "Description Snippet",
            "salary": "Salary"
        }

        # Prepare the dataframe for display
        df_for_display = df.copy()
        if 'url' in df_for_display.columns:
            # Make the title column the link by replacing its content with the URL
            df_for_display["title"] = df_for_display["url"]

        df_for_display["description_snippet"] = df_for_display['description'].str.slice(0, 100) + '...'
        
        # Ensure salary column exists
        if 'salary' not in df_for_display.columns:
            df_for_display['salary'] = "Not Available"

        display_cols = ['Select', 'title', 'company', 'location', 'description_snippet', 'salary']
        
        # Ensure all columns to be displayed exist in the dataframe
        for col in display_cols:
            if col not in df_for_display.columns:
                df_for_display[col] = "Not Available"

        edited_df = st.data_editor(
            df_for_display[display_cols],
            column_config=column_config,
            hide_index=True,
            disabled=['title', 'company', 'location', 'description_snippet', 'salary']
        )
        st.session_state.jobs_df["Select"] = edited_df["Select"]

        if st.button("🌟 Generate Documents for Selected Jobs (Premium)", type="primary"):
            sel = st.session_state.jobs_df.get("Select")
            selected_jobs = st.session_state.jobs_df[sel == True] if sel is not None and hasattr(sel, 'any') else pd.DataFrame()
            if selected_jobs.empty:
                st.warning("Please select at least one job.")
            else:
                st.info(f"Found {len(selected_jobs)} jobs to process...")
                all_generated_files = []
                for index, job in selected_jobs.iterrows():
                    with st.expander(f"Processing: {job['title']} at {job['company']}", expanded=True):
                        try:
                            initial_state = {
                                "candidate_name": candidate_name, "target_position": job['title'], "target_company": job['company'],
                                "target_location": job['location'], "base_resume_text": extract_text_from_pdf(st.session_state.base_resume_bytes), "job_description": job['description'],
                            }
                            final_state = graph.invoke(initial_state)
                            st.success("Successfully generated documents!")
                            all_generated_files.extend([final_state.get('final_pdf_path'), final_state.get('cover_letter_pdf_path')])
                        except Exception as e: st.error(f"Failed to process job: {e}")
                
                if all_generated_files:
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w") as zip_f:
                        for file_path in filter(None, all_generated_files):
                            if file_path and os.path.isfile(file_path):
                                zip_f.write(file_path, os.path.basename(file_path))
                    st.download_button("📥 Download All Premium Files (ZIP)", zip_buffer.getvalue(), "premium_documents.zip", "application/zip", use_container_width=True)

        # LinkedIn Apply: export selected jobs and run apply script
        sel = st.session_state.jobs_df.get("Select")
        selected = st.session_state.jobs_df[sel == True] if sel is not None and hasattr(sel, 'any') else pd.DataFrame()
        linkedin_jobs = pd.DataFrame()
        if not selected.empty and "url" in selected.columns:
            urls = selected["url"].fillna("").astype(str)
            linkedin_jobs = selected[urls.str.contains("linkedin.com", na=False)]
        if not linkedin_jobs.empty:
            st.markdown("---")
            st.subheader("🔗 Apply on LinkedIn")
            st.caption("Export selected LinkedIn jobs and apply using [linkedin-mcp-server](https://github.com/eliasbiondo/linkedin-mcp-server) flow.")
            jobs_export = linkedin_jobs[["title", "company", "location", "description", "url"]].to_dict(orient="records")
            for r in jobs_export:
                r["applyUrl"] = r.get("url", "")
            json_bytes = json.dumps(jobs_export, indent=2).encode()
            st.download_button("📤 Export jobs for LinkedIn apply (JSON)", json_bytes, "linkedin_jobs_to_apply.json", "application/json", key="export_linkedin")
            st.code("python apply_linkedin_jobs.py linkedin_jobs_to_apply.json --no-headless", language="bash")
            st.caption("Set LINKEDIN_EMAIL, LINKEDIN_PASSWORD. Add resume PDF to Master_Resumes/ or set RESUME_PATH.")
            st.caption("⚠️ Only apply to jobs with Fit Decision = Apply (job strongly matches your verified background).")

with tab4:
    st.header("🎯 Live ATS Optimizer")
    st.markdown("""
    **Master Resume → Job → ATS scan → rewrite → re-scan** until internal score = 100.
    Only applies truthful skills from your master resume. Auto-apply only when job is a full fit.
    """)
    live_master_pdf = st.file_uploader("Upload Master Resume (PDF)", type=["pdf"], key="live_master")
    job_source_live = st.selectbox("Job source", ["Manual (paste JD)", "Job URL", "LinkedIn MCP", "Apify"], key="live_source")
    job_url_or_jd = ""
    if job_source_live == "Job URL":
        url_in = st.text_input("Job URL", key="live_url")
        if url_in:
            jd_from_url = scrape_job_url(url_in)
            if not jd_from_url.startswith("Error:"):
                job_url_or_jd = jd_from_url
            else:
                job_url_or_jd = url_in
    elif job_source_live == "Manual (paste JD)":
        job_url_or_jd = st.text_area("Paste Job Description", height=200, key="live_jd")
    else:
        job_url_or_jd = st.text_area("Paste JD (or leave blank to fetch from source)", height=150, key="live_jd_alt")
    target_ats = st.number_input("Target ATS score", min_value=75, max_value=100, value=100, key="live_target")
    truth_safe_live = st.checkbox("Truth-safe mode (only add skills from master resume)", value=True, key="live_truth")
    auto_apply_full_match = st.checkbox("Auto-apply only on full match", value=True, key="live_auto")

    if st.button("🎯 Run Live ATS Optimizer", type="primary", key="live_optimizer_btn"):
        master_bytes = live_master_pdf.read() if live_master_pdf else st.session_state.get("base_resume_bytes")
        if not master_bytes:
            st.error("Upload master resume first (or use one from the sidebar).")
        elif not job_url_or_jd and job_source_live in ("Manual (paste JD)", "Job URL"):
            st.error("Provide job URL or paste JD.")
        else:
            master_text = extract_text_from_pdf(master_bytes)
            if job_source_live == "LinkedIn MCP":
                from providers.linkedin_mcp_jobs import fetch_linkedin_mcp_jobs
                jobs = fetch_linkedin_mcp_jobs(["AI Engineer", "Machine Learning"], max_results=5)
                if not jobs:
                    st.warning("No LinkedIn jobs found. Paste a JD manually in the Job Description area above.")
                else:
                    job_url_or_jd = jobs[0].get("description", "") or str(jobs[0])
                    st.info(f"Using first job: {jobs[0].get('title', '')} at {jobs[0].get('company', '')}")
            elif job_source_live == "Apify":
                finder = EnhancedJobFinder(apify_api_key or "", provider="apify")
                jobs_df = finder.find_jobs_with_apify(master_text, 5)
                if jobs_df.empty:
                    st.warning("No Apify jobs found. Paste a JD manually.")
                else:
                    row = jobs_df.iloc[0]
                    job_url_or_jd = row.get("description", row.get("description_snippet", ""))
                    st.info(f"Using first job: {row.get('title', row.get('position', ''))} at {row.get('company', row.get('companyName', ''))}")

            if job_url_or_jd and job_url_or_jd.strip():
                with st.spinner("Running iterative ATS optimizer..."):
                    try:
                        state = {
                            "candidate_name": candidate_name, "target_position": "AI/ML Engineer", "target_company": "Target",
                            "target_location": "USA", "base_resume_text": master_text, "job_description": str(job_url_or_jd)[:15000],
                            "is_eligible": True,
                        }
                        opt_result = run_iterative_ats_optimizer(
                            state=state, ats_checker=EnhancedATSChecker(),
                            tailor_fn=tailor_resume, humanize_fn=humanize_resume,
                            target_score=int(target_ats), max_attempts=5, truth_safe=truth_safe_live,
                        )
                        master_inv = parse_master_resume(master_text)
                        fit = compute_job_fit_score(str(job_url_or_jd), master_inv, ats_score=opt_result.get("final_ats_score", 0))

                        st.metric("Current ATS Score", f"{opt_result.get('final_ats_score', 0)}%")
                        with st.expander("Missing keywords"):
                            st.write(", ".join(opt_result.get("missing_keywords", [])))
                        with st.expander("Unsupported JD requirements (do not add)"):
                            unsup = fit.get("unsupported_requirements", [])
                            st.write(", ".join(unsup) if unsup else "None")
                        fit_decision = "Apply" if fit.get("apply") else ("Reject" if fit.get("reject") else "Review")
                        st.metric("Fit Decision", fit_decision)
                        if fit.get("reasons"):
                            st.caption("; ".join(fit["reasons"][:3]))

                        st.subheader("Final Tailored Resume")
                        st.text_area("Resume (Markdown)", value=opt_result.get("humanized_resume_text", ""), height=400, disabled=True, key="live_resume_out")
                        # Generate cover letter
                        cl_state = {**state, "tailored_resume_text": opt_result.get("humanized_resume_text", ""), "humanized_resume_text": opt_result.get("humanized_resume_text", "")}
                        cover_letter = generate_cover_letter(cl_state)
                        st.subheader("Cover Letter")
                        st.text_area("Cover Letter", value=cover_letter.get("cover_letter_text", ""), height=200, disabled=True, key="live_cl_out")
                        st.session_state.live_ats_result = opt_result
                        st.session_state.live_fit = fit
                    except Exception as e:
                        st.error(str(e))
                        import traceback
                        st.code(traceback.format_exc())

with tab5:
    st.header("💼 My Application Tracker")
    st.markdown("Track all processed jobs and prepare for interviews.")

    try:
        apps_df = load_applications()
        if apps_df.empty:
            st.info("You haven't processed any applications yet. Use the other tabs to get started!")
        else:
            # Persist edits to the status
            edited_apps_df = st.data_editor(apps_df, column_config={"Status": st.column_config.SelectboxColumn("Status", options=['Applied', 'Interviewing', 'Offer', 'Rejected'])}, hide_index=True)
            if not edited_apps_df.equals(apps_df):
                edited_apps_df.to_csv(application_tracker.APPLICATION_FILE, index=False)
                st.success("Status updated!")

            st.markdown("---")
            st.subheader("🎓 Interview Preparation Assistant")
            app_options = [f"{row.Company} - {row.Position}" for row in edited_apps_df.itertuples()]
            app_to_prep = st.selectbox("Select an application to prepare for:", options=app_options)
            
            if st.button("Generate Interview Prep Guide", type="primary"):
                selected_app_index = app_options.index(app_to_prep)
                selected_app = edited_apps_df.iloc[selected_app_index]
                jd = selected_app.get('Job Description', '') or ''
                resume_bytes = st.session_state.get("base_resume_bytes")
                resume_text = extract_text_from_pdf(resume_bytes) if resume_bytes else "Resume not uploaded. Upload your resume in the sidebar for personalized prep."
                with st.spinner("Your AI career coach is generating a personalized prep guide..."):
                    prep_guide = generate_interview_prep(
                        job_description=jd,
                        resume_text=resume_text,
                        company_name=selected_app.get('Company', '')
                    )
                    st.markdown(prep_guide)
    except Exception as e:
        st.error(f"An error occurred with the application tracker: {e}")
