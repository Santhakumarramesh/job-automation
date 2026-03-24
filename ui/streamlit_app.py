"""
Streamlit app - tabs, forms, display. Calls services instead of agents directly.
"""

import re
import json
import os
import pathlib
import base64
import io
import zipfile
import requests
from bs4 import BeautifulSoup

import streamlit as st
import pandas as pd
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

from agents.state import AgentState
from agents.job_analyzer import analyze_job_description
from agents.job_guard import guard_job_quality
from agents.intelligent_project_generator import intelligent_project_generator

from services.document_service import (
    extract_text_from_pdf,
    tailor,
    humanize_resume_text,
    generate_cover_letter_from_state,
    humanize_cover_letter_text,
    save_documents_to_pdf,
)
from services.ats_service import score_resume, run_iterative_ats, check_fit_gate, run_live_optimizer
from services.application_service import get_applications, log_to_tracker, save_tracker_edits
from services.follow_up_service import list_follow_ups as list_follow_up_queue
from services.application_insights import build_application_insights
from services.job_search_service import get_jobs
from services.profile_service import load_profile
from services.policy_service import policy_from_exported_job
from agents.application_answerer import build_answerer_preview_for_export
from agents.interview_prep_agent import generate_interview_prep

_SCRIPT_DIR = pathlib.Path(__file__).resolve().parent.parent
_CREDS_FILE = os.path.join(_SCRIPT_DIR, ".env")


# --- Helpers ---
def _streamlit_tracker_user_id() -> str:
    """Tag tracker rows from this UI (override with TRACKER_DEFAULT_USER_ID)."""
    return (os.getenv("TRACKER_DEFAULT_USER_ID") or "streamlit-local").strip()


def scrape_job_url(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, "html.parser")
        for script in soup(["script", "style", "nav", "footer"]):
            script.extract()
        return soup.get_text(separator=" ", strip=True)
    except Exception as e:
        return f"Error: {e}"


def _extract_location_from_jd(jd_text):
    if not jd_text or jd_text.startswith("Error:"):
        return ""
    text = jd_text[:3000]
    for pat in [
        r"Location[:\s]+([^\n|]+?)(?:\n|$)",
        r"Work Location[:\s]+([^\n|]+?)(?:\n|$)",
        r"Based in[:\s]+([^\n|]+?)(?:\n|$)",
        r"Office Location[:\s]+([^\n|]+?)(?:\n|$)",
        r"Job Location[:\s]+([^\n|]+?)(?:\n|$)",
    ]:
        m = re.search(pat, text, re.I)
        if m:
            loc = m.group(1).strip()
            if len(loc) < 80:
                return loc
    if re.search(r"\bRemote\b", text, re.I):
        return "Remote"
    return ""


def display_pdf(file_path):
    with open(file_path, "rb") as f:
        base64_pdf = base64.b64encode(f.read()).decode("utf-8")
    pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800" type="application/pdf"></iframe>'
    st.markdown(pdf_display, unsafe_allow_html=True)


def _load_saved_creds():
    load_dotenv(_CREDS_FILE)
    return {
        "openai": os.getenv("OPENAI_API_KEY", ""),
        "apify": os.getenv("APIFY_API_KEY") or os.getenv("APIFY_API_TOKEN", ""),
        "name": os.getenv("CANDIDATE_NAME", "Santhakumar Ramesh"),
    }


def _save_creds(openai_key: str, apify_key: str, name: str):
    skip_prefixes = ("OPENAI_API_KEY=", "APIFY_API_KEY=", "APIFY_API_TOKEN=", "CANDIDATE_NAME=")
    lines = []
    if os.path.isfile(_CREDS_FILE):
        with open(_CREDS_FILE, "r") as f:
            for line in f:
                if not any(line.strip().startswith(p) for p in skip_prefixes):
                    lines.append(line.rstrip())
    with open(_CREDS_FILE, "w") as f:
        if openai_key:
            f.write(f"OPENAI_API_KEY={openai_key}\n")
        if apify_key:
            f.write(f"APIFY_API_TOKEN={apify_key}\n")
        if name:
            f.write(f"CANDIDATE_NAME={name}\n")
        for line in lines:
            if line:
                f.write(line + "\n")


# --- Graph nodes (call services) ---
def enhanced_ats_scorer_node(state: AgentState):
    st.write(f"🔬 Running Semantic ATS Analysis for {state['target_company']}...")
    result = score_resume(state, target_score=100)
    st.write(f"Semantic ATS Score for {state['target_company']}: {result['initial_ats_score']}%")
    return result


def iterative_ats_optimizer_node(state: AgentState):
    st.write(f"🔄 Running iterative ATS optimizer (target 100, truth-safe) for {state['target_company']}...")
    result = run_iterative_ats(state, target_score=100, max_attempts=5, truth_safe=True)
    st.write(f"✅ Iterative ATS complete. Score: {result['final_ats_score']}%")
    if result.get("truth_safe_ats_ceiling") is not None:
        st.metric("Truth-safe ATS ceiling (est.)", f"{result['truth_safe_ats_ceiling']}%")
        st.caption(result.get("truth_safe_ceiling_reason", ""))
    return result


def fit_gate_node(state: AgentState):
    st.write(f"🎯 Running master-resume fit gate for {state['target_company']}...")
    result = check_fit_gate(state)
    st.write(f"Fit decision: **{result['fit_decision'].upper()}** (score: {result.get('job_fit_score', 0)})")
    if result.get("is_eligible") is False:
        st.warning(f"Job rejected: {result.get('eligibility_reason', '')}")
    return result


def log_application_node(state: AgentState):
    return log_to_tracker(state)


def build_graph(use_iterative_ats: bool = False):
    workflow = StateGraph(AgentState)
    workflow.add_node("guard_job", guard_job_quality)
    workflow.add_node("analyze_jd", analyze_job_description)
    workflow.add_node("fit_gate", fit_gate_node)
    workflow.add_node("score_resume_enhanced", enhanced_ats_scorer_node)
    workflow.add_node("iterative_ats", iterative_ats_optimizer_node)
    workflow.add_node("edit_resume", tailor)
    workflow.add_node("humanize_resume", humanize_resume_text)
    workflow.add_node("generate_project_intelligent", intelligent_project_generator)
    workflow.add_node("generate_cover_letter", generate_cover_letter_from_state)
    workflow.add_node("humanize_cover_letter", humanize_cover_letter_text)
    workflow.add_node("save_final_documents", save_documents_to_pdf)
    workflow.add_node("log_application_node", log_application_node)

    def check_guard(state): return "analyze_jd" if state.get("is_eligible", True) else END
    def check_fit_gate_fn(state): return "continue" if state.get("is_eligible", True) else END
    def check_ats_score(state): return "generate_project_intelligent" if state.get("initial_ats_score", 0) >= 75 else "edit_resume"

    workflow.set_entry_point("guard_job")
    workflow.add_conditional_edges("guard_job", check_guard, {"analyze_jd": "analyze_jd", END: END})
    workflow.add_edge("analyze_jd", "fit_gate")
    workflow.add_conditional_edges("fit_gate", check_fit_gate_fn, {"continue": "iterative_ats" if use_iterative_ats else "score_resume_enhanced", END: END})
    if use_iterative_ats:
        workflow.add_edge("iterative_ats", "generate_project_intelligent")
    else:
        workflow.add_conditional_edges("score_resume_enhanced", check_ats_score, {"generate_project_intelligent": "generate_project_intelligent", "edit_resume": "edit_resume"})
        workflow.add_edge("edit_resume", "humanize_resume")
        workflow.add_edge("humanize_resume", "generate_project_intelligent")
    workflow.add_edge("generate_project_intelligent", "generate_cover_letter")
    workflow.add_edge("generate_cover_letter", "humanize_cover_letter")
    workflow.add_edge("humanize_cover_letter", "save_final_documents")
    workflow.add_edge("save_final_documents", "log_application_node")
    workflow.add_edge("log_application_node", END)
    return workflow.compile()


def run():
    """Main entry: render full Streamlit app."""
    load_dotenv()
    st.set_page_config(page_title="Career Co-Pilot Pro", page_icon="🚀", layout="wide")

    st.title("🚀 Career Co-Pilot Pro")
    st.markdown("LLM-Powered Job Finding, Semantic Analysis, and Interview Preparation")

    saved = _load_saved_creds()
    st.sidebar.header("🔑 API Configuration")
    openai_api_key = st.sidebar.text_input("OpenAI API Key", type="password", value=saved["openai"], key="openai_key")
    apify_api_key = st.sidebar.text_input("Apify API Key", type="password", value=saved["apify"], key="apify_key")

    st.sidebar.markdown("---")
    st.sidebar.subheader("👤 Candidate Information")
    candidate_name = st.sidebar.text_input("Your Name", value=saved["name"], key="candidate_name")

    MASTER_RESUMES_DIR = _SCRIPT_DIR / "Master_Resumes"
    master_pdfs = list(MASTER_RESUMES_DIR.glob("*.pdf")) if MASTER_RESUMES_DIR.exists() else []
    if master_pdfs:
        master_choice = st.sidebar.selectbox("Or pick from Master_Resumes", ["— Upload below —"] + [p.name for p in master_pdfs])
        if master_choice != "— Upload below —":
            sel_path = MASTER_RESUMES_DIR / master_choice
            if sel_path.exists():
                st.session_state.base_resume_bytes = sel_path.read_bytes()

    base_resume = st.sidebar.file_uploader("Upload Your Base Resume (PDF)", type=["pdf"])
    if base_resume:
        st.session_state.base_resume_bytes = base_resume.read()

    with st.sidebar.expander("📋 Application Profile", expanded=False):
        try:
            from services.profile_service import (
                ensure_profile_exists,
                format_application_locations_summary,
                load_profile,
                validate_profile,
            )
            from agents.application_answerer import answer_question_structured
            if ensure_profile_exists():
                profile = load_profile()
                if profile.get("full_name"):
                    st.caption(f"✓ {profile.get('full_name', '')[:30]}...")
                else:
                    st.caption("Edit config/candidate_profile.json")
                w = validate_profile(profile)
                if w:
                    for msg in w[:3]:
                        st.caption(f"⚠️ {msg}")
                else:
                    st.caption("Profile OK")
                loc_s = format_application_locations_summary(profile)
                if loc_s:
                    st.caption(f"📍 application_locations: {loc_s[:220]}{'…' if len(loc_s) > 220 else ''}")
                sample_q = st.text_input("Test question", placeholder="e.g. Do you require sponsorship?", key="profile_test_q")
                if sample_q:
                    meta = answer_question_structured(sample_q, profile=profile, master_resume_text="")
                    ans = meta["answer"]
                    st.caption(f"→ {ans[:80]}{'...' if len(ans) > 80 else ''}")
                    if meta["manual_review_required"]:
                        rc = ", ".join(meta["reason_codes"][:6]) or "review suggested"
                        st.caption(f"⚠️ manual_review_required — {rc}")
        except ImportError:
            st.caption("Copy config/candidate_profile.example.json to candidate_profile.json")

    if st.sidebar.button("💾 Save credentials (no re-enter next time)", use_container_width=True):
        _save_creds(openai_api_key, apify_api_key, candidate_name)
        st.sidebar.success("Saved to .env – reload the page to confirm.")

    use_iterative_ats = st.sidebar.checkbox(
        "Use iterative ATS (target 100, truth-safe)",
        value=True,
        help="Loop until internal ATS score = 100, using only skills from master resume.",
    )

    st.sidebar.markdown("---")
    if not openai_api_key:
        st.error("Please provide OpenAI API key in the sidebar.")
        st.stop()
    # Apify required only for Apify / Both; LinkedIn MCP only does not need it
    if not apify_api_key:
        st.warning("Apify key missing. Job Finder with Apify/Both and Live ATS with Apify will be disabled. LinkedIn MCP works without it.")

    os.environ["OPENAI_API_KEY"] = openai_api_key
    os.environ["APIFY_API_KEY"] = apify_api_key

    graph = build_graph(use_iterative_ats=use_iterative_ats)

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
                            "candidate_name": candidate_name,
                            "target_position": target_position,
                            "target_company": target_company,
                            "target_location": target_location,
                            "base_resume_text": extract_text_from_pdf(st.session_state.base_resume_bytes),
                            "job_description": jd_text,
                            "user_id": _streamlit_tracker_user_id(),
                        }
                        final_state = graph.invoke(initial_state)
                        st.success("Pipeline Complete!")
                        st.metric("Final Semantic ATS Score", f"{final_state.get('initial_ats_score', final_state.get('final_ats_score', 0))}%")
                        if final_state.get("truth_safe_ats_ceiling") is not None:
                            st.metric("Truth-safe ceiling (est.)", f"{final_state['truth_safe_ats_ceiling']}%")
                            st.caption(final_state.get("truth_safe_ceiling_reason", ""))
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
                    except Exception as e:
                        st.error(f"An error occurred: {e}")

    with tab2:
        st.header("🚀 Batch Process Jobs from URLs")
        st.markdown("Paste job URLs (one per line). The system will scrape each job description and run the full automation pipeline.")
        urls_input = st.text_area("Paste Job URLs Here", height=200, key="batch_urls")

        if st.button("Run Batch URL Processing", type="primary", key="batch_process_button"):
            if not all([st.session_state.get("base_resume_bytes"), urls_input]):
                st.error("Please upload your resume and paste at least one URL.")
            else:
                urls = [u.strip() for u in urls_input.split("\n") if u.strip()]
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
                            except Exception:
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
                                "user_id": _streamlit_tracker_user_id(),
                            }
                            final_state = graph.invoke(initial_state)
                            st.success(f"Successfully generated documents for {company_name_from_url}!")
                            all_generated_files.extend([final_state.get("final_pdf_path"), final_state.get("cover_letter_pdf_path")])
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
            help="Apify: AI Deep Job Search. LinkedIn MCP: requires linkedin-mcp-server running.",
        )
        provider_map = {"Apify": "apify", "LinkedIn MCP": "linkedin_mcp", "Both": "both"}
        provider = provider_map[job_source]
        max_jobs = st.slider("Max jobs to find", 10, 200, 50)

        job_filters = None
        if provider in ("linkedin_mcp", "both"):
            with st.expander("LinkedIn filters", expanded=False):
                easy_apply_filter = st.checkbox(
                    "Easy Apply only",
                    value=True,
                    key="filter_easy_apply",
                    help="Default ON. Auto-apply only works with Easy Apply jobs. Non–Easy Apply jobs get docs for manual apply.",
                )
                date_posted = st.selectbox("Date posted", ["", "24h", "1w", "1m"], key="filter_date_posted")
                sort_order = st.selectbox("Sort by", ["", "most_recent", "most_relevant"], key="filter_sort")
            try:
                from providers.base_provider import SearchFilters
                job_filters = SearchFilters(easy_apply=easy_apply_filter, date_posted=date_posted or "", sort_order=sort_order or "")
            except ImportError:
                pass

        needs_apify = provider in ("apify", "both")
        if needs_apify and not apify_api_key:
            st.warning("Apify API key required for this source.")
        btn_disabled = needs_apify and not apify_api_key
        if st.button("Find Jobs", type="primary", disabled=btn_disabled):
            if not st.session_state.get("base_resume_bytes"):
                st.error("Upload resume first.")
            else:
                with st.spinner(f"Finding jobs via {job_source}..."):
                    jobs_df = get_jobs(
                        resume_text=extract_text_from_pdf(st.session_state.base_resume_bytes),
                        provider=provider,
                        apify_api_key=apify_api_key or "",
                        max_results=max_jobs,
                        filters=job_filters,
                    )
                    if not jobs_df.empty:
                        st.success(f"Found {len(jobs_df)} jobs!")
                        for col in ["title", "company", "location", "description"]:
                            if col not in jobs_df.columns:
                                jobs_df[col] = "Not Available"
                        st.session_state.jobs_df = jobs_df

        if "jobs_df" in st.session_state:
            df = st.session_state.jobs_df
            col_map = {"position": "title", "jobTitle": "title", "companyName": "company", "company_name": "company"}
            for old, new in col_map.items():
                if old in df.columns and new not in df.columns:
                    df[new] = df[old]
            if "Select" not in df.columns:
                df["Select"] = False
            if "easy_apply" not in df.columns:
                df["easy_apply"] = False
            if "easy_apply_filter_used" not in df.columns:
                df["easy_apply_filter_used"] = False
            if "easy_apply_confirmed" not in df.columns:
                df["easy_apply_confirmed"] = False
            if "apply_mode" not in df.columns:
                df["apply_mode"] = "manual_assist"
            for col in ["title", "company", "location", "description"]:
                if col not in df.columns:
                    df[col] = "Not Available"
            st.session_state.jobs_df = df

            column_config = {
                "Select": st.column_config.CheckboxColumn("Select", default=False),
                "title": st.column_config.LinkColumn("Job Title", display_text="Apply ↗", width="medium"),
                "company": "Company",
                "location": "Location",
                "description_snippet": "Description Snippet",
                "salary": "Salary",
            }
            df_for_display = df.copy()
            if "url" in df_for_display.columns:
                df_for_display["title"] = df_for_display["url"]
            df_for_display["description_snippet"] = df_for_display["description"].str.slice(0, 100) + "..."
            if "salary" not in df_for_display.columns:
                df_for_display["salary"] = "Not Available"
            display_cols = ["Select", "title", "company", "location", "description_snippet", "salary"]
            for col in display_cols:
                if col not in df_for_display.columns:
                    df_for_display[col] = "Not Available"

            edited_df = st.data_editor(
                df_for_display[display_cols],
                column_config=column_config,
                hide_index=True,
                disabled=["title", "company", "location", "description_snippet", "salary"],
            )
            st.session_state.jobs_df["Select"] = edited_df["Select"]

            sel_for_gen = st.session_state.jobs_df.get("Select")
            selected_for_gen = st.session_state.jobs_df[sel_for_gen == True] if sel_for_gen is not None and hasattr(sel_for_gen, "any") else pd.DataFrame()
            if not selected_for_gen.empty:
                apply_mode_col = selected_for_gen.get("apply_mode", pd.Series(["manual_assist"] * len(selected_for_gen)))
                n_auto = (apply_mode_col == "auto_easy_apply").sum() if hasattr(apply_mode_col, "sum") else 0
                n_manual = len(selected_for_gen) - n_auto
                if n_manual > 0:
                    st.caption(f"📋 {n_manual} of {len(selected_for_gen)} selected are manual-assist (apply_mode≠auto_easy_apply). {n_auto} ready for auto-apply.")
                if not selected_for_gen.empty:
                    with st.expander("📊 Blocker summary for selected jobs"):
                        for _, row in selected_for_gen.head(10).iterrows():
                            comp = row.get("company", "")
                            tit = row.get("title", "")
                            am = row.get("apply_mode", "—")
                            fd = row.get("fit_decision", "—")
                            ats = row.get("ats_score", row.get("final_ats_score", "—"))
                            unsup = row.get("unsupported_requirements", [])
                            st.caption(f"**{comp} / {tit}** — apply_mode: {am} | fit: {fd} | ATS: {ats} | unsupported: {unsup if unsup else '—'}")
            if st.button("🌟 Generate Documents for Selected Jobs (Premium)", type="primary"):
                sel = st.session_state.jobs_df.get("Select")
                selected_jobs = st.session_state.jobs_df[sel == True] if sel is not None and hasattr(sel, "any") else pd.DataFrame()
                if selected_jobs.empty:
                    st.warning("Please select at least one job.")
                else:
                    st.info(f"Found {len(selected_jobs)} jobs to process...")
                    all_generated_files = []
                    for index, job in selected_jobs.iterrows():
                        with st.expander(f"Processing: {job['title']} at {job['company']}", expanded=True):
                            try:
                                initial_state = {
                                    "candidate_name": candidate_name,
                                    "target_position": job["title"],
                                    "target_company": job["company"],
                                    "target_location": job["location"],
                                    "base_resume_text": extract_text_from_pdf(st.session_state.base_resume_bytes),
                                    "job_description": job["description"],
                                    "user_id": _streamlit_tracker_user_id(),
                                }
                                final_state = graph.invoke(initial_state)
                                st.success("Successfully generated documents!")
                                all_generated_files.extend([final_state.get("final_pdf_path"), final_state.get("cover_letter_pdf_path")])
                            except Exception as e:
                                st.error(f"Failed to process job: {e}")
                    if all_generated_files:
                        zip_buffer = io.BytesIO()
                        with zipfile.ZipFile(zip_buffer, "w") as zip_f:
                            for file_path in filter(None, all_generated_files):
                                if file_path and os.path.isfile(file_path):
                                    zip_f.write(file_path, os.path.basename(file_path))
                        st.download_button("📥 Download All Premium Files (ZIP)", zip_buffer.getvalue(), "premium_documents.zip", "application/zip", use_container_width=True)

            sel = st.session_state.jobs_df.get("Select")
            selected = st.session_state.jobs_df[sel == True] if sel is not None and hasattr(sel, "any") else pd.DataFrame()
            linkedin_jobs = pd.DataFrame()
            if not selected.empty and "url" in selected.columns:
                urls = selected["url"].fillna("").astype(str)
                linkedin_jobs = selected[urls.str.contains("linkedin.com", na=False)].copy()

            if not linkedin_jobs.empty:
                st.markdown("---")
                st.subheader("🔗 Two-Lane Apply Strategy")
                with st.expander("📋 Decision rules", expanded=True):
                    st.markdown("""
                    **Lane 1 — Auto-apply** (Easy Apply only):
                    - Easy Apply + fit ≥ 85 + truthful match + no blocker → auto-submit
                    - Use export below and `scripts/apply_linkedin_jobs.py`

                    **Lane 2 — Manual-assist** (external portals):
                    - Non–Easy Apply (Workday, Greenhouse, Lever) → prepare docs only
                    - Use "Generate Documents" above, then apply manually
                    """)
                apply_mode_col = linkedin_jobs["apply_mode"] if "apply_mode" in linkedin_jobs.columns else pd.Series(["manual_assist"] * len(linkedin_jobs))
                auto_apply_jobs = linkedin_jobs[apply_mode_col == "auto_easy_apply"] if (apply_mode_col == "auto_easy_apply").any() else pd.DataFrame()
                manual_lane_jobs = linkedin_jobs[apply_mode_col != "auto_easy_apply"]
                if not auto_apply_jobs.empty:
                    st.caption(f"✅ **{len(auto_apply_jobs)} Easy Apply** job(s) in auto lane (before answerer preview).")
                    cols_export = [
                        "title",
                        "company",
                        "location",
                        "description",
                        "url",
                        "apply_mode",
                        "easy_apply_confirmed",
                        "fit_decision",
                        "ats_score",
                        "final_ats_score",
                        "unsupported_requirements",
                    ]
                    cols_export = [c for c in cols_export if c in auto_apply_jobs.columns]
                    jobs_export = auto_apply_jobs[cols_export].to_dict(orient="records")
                    master_txt = ""
                    try:
                        if st.session_state.get("base_resume_bytes"):
                            master_txt = extract_text_from_pdf(st.session_state.base_resume_bytes)
                    except Exception:
                        master_txt = ""
                    prof = load_profile()
                    for r in jobs_export:
                        r["applyUrl"] = r.get("url", "")
                        r["easy_apply"] = True
                        r["easy_apply_confirmed"] = True
                        ar, pend = build_answerer_preview_for_export(
                            prof, r, master_resume_text=master_txt, use_llm=False
                        )
                        r["answerer_review"] = ar
                        r["answerer_manual_review_required"] = pend
                        mode, reason = policy_from_exported_job(r)
                        r["apply_mode"] = mode
                        r["policy_reason"] = reason
                    auto_final = [r for r in jobs_export if r.get("apply_mode") == "auto_easy_apply"]
                    dropped = len(jobs_export) - len(auto_final)
                    if dropped:
                        st.warning(
                            f"{dropped} job(s) moved to **manual_assist** after answerer preview "
                            f"(see `policy_reason` / `answerer_manual_review_required`). "
                            "They are excluded from this JSON. Fix profile short answers or apply manually."
                        )
                    if not auto_final:
                        st.error(
                            "No jobs remain in the auto-apply lane after answerer + policy check. "
                            "Complete `config/candidate_profile.json` (short answers, links, salary, etc.) or use manual lane."
                        )
                    else:
                        st.caption(
                            f"📤 Exporting **{len(auto_final)}** job(s) with answerer preview + `policy_reason` for scripts/MCP."
                        )
                        json_bytes = json.dumps(auto_final, indent=2, default=str).encode()
                        st.download_button(
                            "📤 Export Easy Apply jobs for auto-apply (JSON)",
                            json_bytes,
                            "linkedin_easy_apply_jobs.json",
                            "application/json",
                            key="export_linkedin",
                        )
                    st.code("python scripts/apply_linkedin_jobs.py linkedin_easy_apply_jobs.json --no-headless\n# --dry-run to fill without submitting | --rate-limit 120", language="bash")
                    st.caption("Set LINKEDIN_EMAIL, LINKEDIN_PASSWORD. Export runs a deterministic answerer preview; jobs with manual_review_required become manual_assist in policy.")
                else:
                    if not manual_lane_jobs.empty:
                        st.info(f"📋 **{len(manual_lane_jobs)}** selected job(s) are not Easy Apply. Use \"Generate Documents\" above to prepare resume + cover letter for manual apply.")
                    else:
                        st.warning("No Easy Apply jobs in selection. Enable \"Easy Apply only\" in LinkedIn filters and search again for auto-apply.")

    with tab4:
        st.header("🎯 Live ATS Optimizer")
        st.markdown("**Master Resume → Job → ATS scan → rewrite → re-scan** until internal score = 100. Truth-safe.")
        live_master_pdf = st.file_uploader("Upload Master Resume (PDF)", type=["pdf"], key="live_master")
        job_source_live = st.selectbox("Job source", ["Manual (paste JD)", "Job URL", "LinkedIn MCP", "Apify"], key="live_source")
        job_url_or_jd = ""
        if job_source_live == "Job URL":
            url_in = st.text_input("Job URL", key="live_url")
            if url_in:
                jd_from_url = scrape_job_url(url_in)
                job_url_or_jd = jd_from_url if not jd_from_url.startswith("Error:") else url_in
        elif job_source_live == "Manual (paste JD)":
            job_url_or_jd = st.text_area("Paste Job Description", height=200, key="live_jd")
        else:
            job_url_or_jd = st.text_area("Paste JD (or leave blank to fetch from source)", height=150, key="live_jd_alt")
        target_ats = st.number_input("Target ATS score", min_value=75, max_value=100, value=100, key="live_target")
        truth_safe_live = st.checkbox("Truth-safe mode", value=True, key="live_truth")
        auto_apply_full_match = st.checkbox("Auto-apply only on full match", value=True, key="live_auto")

        if st.button("🎯 Run Live ATS Optimizer", type="primary", key="live_optimizer_btn"):
            master_bytes = live_master_pdf.read() if live_master_pdf else st.session_state.get("base_resume_bytes")
            if not master_bytes:
                st.error("Upload master resume first.")
            elif not job_url_or_jd and job_source_live in ("Manual (paste JD)", "Job URL"):
                st.error("Provide job URL or paste JD.")
            else:
                master_text = extract_text_from_pdf(master_bytes)
                if job_source_live == "LinkedIn MCP":
                    from providers.linkedin_mcp_jobs import fetch_linkedin_mcp_jobs
                    jobs = fetch_linkedin_mcp_jobs(["AI Engineer", "Machine Learning"], max_results=5)
                    if jobs:
                        job_url_or_jd = jobs[0].get("description", "") or str(jobs[0])
                        st.info(f"Using first job: {jobs[0].get('title', '')} at {jobs[0].get('company', '')}")
                    else:
                        st.warning("No LinkedIn jobs found. Paste JD manually.")
                elif job_source_live == "Apify":
                    jobs_df = get_jobs(master_text, provider="apify", apify_api_key=apify_api_key or "", max_results=5)
                    if not jobs_df.empty:
                        row = jobs_df.iloc[0]
                        job_url_or_jd = row.get("description", row.get("description_snippet", ""))
                        st.info(f"Using first job: {row.get('title', row.get('position', ''))} at {row.get('company', row.get('companyName', ''))}")
                    else:
                        st.warning("No Apify jobs found. Paste JD manually.")

                if job_url_or_jd and job_url_or_jd.strip():
                    with st.spinner("Running iterative ATS optimizer..."):
                        try:
                            state = {
                                "candidate_name": candidate_name,
                                "target_position": "AI/ML Engineer",
                                "target_company": "Target",
                                "target_location": "USA",
                                "base_resume_text": master_text,
                                "job_description": str(job_url_or_jd)[:15000],
                                "is_eligible": True,
                            }
                            opt_result = run_live_optimizer(state, target_ats=int(target_ats), truth_safe=truth_safe_live)
                            st.metric("Current ATS Score", f"{opt_result.get('final_ats_score', 0)}%")
                            if opt_result.get("truth_safe_ats_ceiling") is not None:
                                st.metric("Truth-safe ceiling (est.)", f"{opt_result['truth_safe_ats_ceiling']}%")
                                st.caption(opt_result.get("truth_safe_ceiling_reason", ""))
                            with st.expander("Missing keywords"):
                                st.write(", ".join(opt_result.get("missing_keywords", [])))
                            with st.expander("Unsupported JD requirements"):
                                unsup = opt_result.get("unsupported_requirements", [])
                                st.write(", ".join(unsup) if unsup else "None")
                            st.metric("Fit Decision", opt_result.get("fit_decision", ""))
                            if opt_result.get("fit_reasons"):
                                st.caption("; ".join(opt_result["fit_reasons"][:3]))
                            st.subheader("Final Tailored Resume")
                            st.text_area("Resume (Markdown)", value=opt_result.get("humanized_resume_text", ""), height=400, disabled=True, key="live_resume_out")
                            cl_state = {**state, "tailored_resume_text": opt_result.get("humanized_resume_text", ""), "humanized_resume_text": opt_result.get("humanized_resume_text", "")}
                            cover_letter = generate_cover_letter_from_state(cl_state)
                            st.subheader("Cover Letter")
                            st.text_area("Cover Letter", value=cover_letter.get("cover_letter_text", ""), height=200, disabled=True, key="live_cl_out")
                            st.session_state.live_ats_result = opt_result
                        except Exception as e:
                            st.error(str(e))
                            import traceback
                            st.code(traceback.format_exc())

    with tab5:
        st.header("💼 My Application Tracker")
        st.markdown("Track all processed jobs and prepare for interviews.")
        try:
            apps_df = get_applications()
            if apps_df.empty:
                st.info("You haven't processed any applications yet. Use the other tabs to get started!")
            else:
                display_df = apps_df.copy()
                if "company" in display_df.columns and "Company" not in display_df.columns:
                    display_df = display_df.rename(columns={"company": "Company", "position": "Position", "status": "Status", "job_description": "Job Description"})
                status_col = "Status" if "Status" in display_df.columns else "status"
                _iv_opts = ["", "none", "scheduled", "completed", "advanced", "rejected", "withdrew", "no_show"]
                _of_opts = ["", "none", "pending", "extended", "accepted", "declined", "ghosted"]
                col_cfg = {
                    status_col: st.column_config.SelectboxColumn(
                        "Status", options=["Applied", "Interviewing", "Offer", "Rejected"]
                    ),
                }
                if "interview_stage" in display_df.columns:
                    col_cfg["interview_stage"] = st.column_config.SelectboxColumn(
                        "Interview stage", options=_iv_opts, help="Pipeline tracking (insights + correlations)"
                    )
                if "offer_outcome" in display_df.columns:
                    col_cfg["offer_outcome"] = st.column_config.SelectboxColumn(
                        "Offer outcome", options=_of_opts, help="Set when you have an offer decision"
                    )
                edited_apps_df = st.data_editor(display_df, column_config=col_cfg, hide_index=True)
                if not edited_apps_df.equals(display_df):
                    save_tracker_edits(edited_apps_df)
                    st.success("Status updated!")

                st.markdown("---")
                st.subheader("📌 Follow-up queue")
                st.caption("Rows with a scheduled follow-up, sorted by priority (ATS, fit, recency, overdue).")
                try:
                    fq = list_follow_up_queue(
                        _streamlit_tracker_user_id(),
                        due_only=False,
                        include_snoozed=True,
                        limit=80,
                        sort_by_priority=True,
                    )
                    if fq:
                        fq_df = pd.DataFrame(fq)
                        show_cols = [
                            c
                            for c in (
                                "follow_up_priority_score",
                                "follow_up_at",
                                "follow_up_status",
                                "company",
                                "position",
                                "ats_score",
                                "fit_decision",
                                "follow_up_note",
                                "job_url",
                            )
                            if c in fq_df.columns
                        ]
                        st.dataframe(fq_df[show_cols], hide_index=True, use_container_width=True)
                    else:
                        st.info("No active follow-ups. Set `follow_up_at` on a tracker row (or via API) to appear here.")
                except Exception as fe:
                    st.warning(f"Could not load follow-up queue: {fe}")

                with st.expander("📈 Application insights (Phase 13 + answerer QA)", expanded=False):
                    st.caption("Tracker aggregates, answerer_review rollups from QA JSON, and hints.")
                    try:
                        ins = build_application_insights(None, include_audit=False)
                        tr = ins.get("tracker") or {}
                        ar = ins.get("answerer_review") or {}
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("Tracker rows", int(tr.get("total") or 0))
                        ats = tr.get("ats") or {}
                        c2.metric("Avg ATS (logged)", f"{ats.get('mean')}" if ats.get("mean") is not None else "—")
                        c3.metric("ATS values", int(ats.get("count_numeric") or 0))
                        c4.metric("Rows w/ answerer QA", int(ar.get("tracker_rows_with_answerer_review") or 0))
                        if int(ar.get("tracker_rows_with_manual_review_flag") or 0) > 0:
                            st.caption(
                                f"Manual-review flags in QA: **{ar.get('tracker_rows_with_manual_review_flag')}** application(s)"
                            )
                        rc = ar.get("reason_code_counts") or {}
                        if rc:
                            st.caption("Top answerer reason codes (from apply runner)")
                            rc_df = pd.DataFrame(
                                [{"reason_code": k, "count": v} for k, v in sorted(rc.items(), key=lambda x: -x[1])[:10]]
                            )
                            st.dataframe(rc_df, hide_index=True, use_container_width=True)
                        for s in ins.get("suggestions") or []:
                            st.markdown(f"- {s}")
                        bpr = tr.get("by_policy_reason") or {}
                        if bpr:
                            st.caption("Top policy reasons")
                            pr_df = pd.DataFrame(
                                [{"reason": k, "count": v} for k, v in sorted(bpr.items(), key=lambda x: -x[1])[:12]]
                            )
                            st.dataframe(pr_df, hide_index=True, use_container_width=True)
                        xtabs = tr.get("crosstabs") or {}
                        sp = xtabs.get("submission_status_by_policy_reason") or []
                        if sp:
                            st.caption("Submission status × policy reason (top pairs)")
                            st.dataframe(pd.DataFrame(sp), hide_index=True, use_container_width=True)
                        sm = xtabs.get("submission_status_by_apply_mode") or []
                        if sm:
                            st.caption("Submission status × apply mode")
                            st.dataframe(pd.DataFrame(sm), hide_index=True, use_container_width=True)
                        ap = xtabs.get("apply_mode_by_policy_reason") or []
                        if ap:
                            st.caption("Apply mode × policy reason")
                            st.dataframe(pd.DataFrame(ap), hide_index=True, use_container_width=True)
                        by_iv = tr.get("by_interview_stage") or {}
                        by_of = tr.get("by_offer_outcome") or {}
                        if by_iv:
                            st.caption("Interview stage (tracker)")
                            st.dataframe(
                                pd.DataFrame([{"stage": k, "count": v} for k, v in sorted(by_iv.items(), key=lambda x: -x[1])[:15]]),
                                hide_index=True,
                                use_container_width=True,
                            )
                        if by_of:
                            st.caption("Offer outcome (tracker)")
                            st.dataframe(
                                pd.DataFrame([{"outcome": k, "count": v} for k, v in sorted(by_of.items(), key=lambda x: -x[1])[:15]]),
                                hide_index=True,
                                use_container_width=True,
                            )
                        pc = tr.get("pipeline_correlations") or {}
                        pacc = pc.get("policy_reason_when_offer_accepted") or {}
                        if pacc:
                            st.caption("Policy reasons when offer accepted")
                            st.dataframe(
                                pd.DataFrame([{"policy_reason": k, "count": v} for k, v in sorted(pacc.items(), key=lambda x: -x[1])[:10]]),
                                hide_index=True,
                                use_container_width=True,
                            )
                    except Exception as ie:
                        st.warning(str(ie))

                st.markdown("---")
                st.subheader("🎓 Interview Preparation Assistant")
                company_col = "Company" if "Company" in edited_apps_df.columns else "company"
                position_col = "Position" if "Position" in edited_apps_df.columns else "position"
                app_options = [f"{getattr(row, company_col, '')} - {getattr(row, position_col, '')}" for row in edited_apps_df.itertuples()]
                app_to_prep = st.selectbox("Select an application to prepare for:", options=app_options)

                if st.button("Generate Interview Prep Guide", type="primary"):
                    selected_app_index = app_options.index(app_to_prep)
                    selected_app = edited_apps_df.iloc[selected_app_index]
                    jd = selected_app.get("Job Description", selected_app.get("job_description", "")) or ""
                    resume_bytes = st.session_state.get("base_resume_bytes")
                    resume_text = extract_text_from_pdf(resume_bytes) if resume_bytes else "Resume not uploaded."
                    with st.spinner("Generating personalized prep guide..."):
                        prep_guide = generate_interview_prep(
                            job_description=jd,
                            resume_text=resume_text,
                            company_name=selected_app.get("Company", selected_app.get("company", "")),
                        )
                        st.markdown(prep_guide)
        except Exception as e:
            st.error(f"An error occurred with the application tracker: {e}")
