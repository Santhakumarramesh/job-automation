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
from urllib.parse import quote
from bs4 import BeautifulSoup

import streamlit as st
import pandas as pd
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

from agents.state import AgentState
from agents.job_analyzer import analyze_job_description
from agents.job_guard import guard_job_quality
from agents.intelligent_project_generator import intelligent_project_generator
from agents.application_answerer import CANONICAL_SCREENING_FIELD_LABELS

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
from services.application_decision import (
    build_application_decision,
    safe_auto_apply_precondition_checklist,
)
from services.policy_service import enrich_job_dict_for_policy_export
from agents.interview_prep_agent import generate_interview_prep

_SCRIPT_DIR = pathlib.Path(__file__).resolve().parent.parent
_CREDS_FILE = os.path.join(_SCRIPT_DIR, ".env")


# --- Helpers ---
def _df_row_to_plain_dict(row: pd.Series) -> dict:
    """DataFrame row → JSON-friendly dict (NaN → empty string / False)."""
    out: dict = {}
    for k, v in row.items():
        try:
            if pd.isna(v):
                out[k] = False if k == "answerer_manual_review_required" else ""
            else:
                out[k] = v
        except (TypeError, ValueError):
            out[k] = v
    return out


def _parse_application_decision_cell(val) -> dict:
    """Parse tracker ``application_decision`` JSON cell; empty dict if missing/invalid."""
    if val is None:
        return {}
    try:
        if pd.isna(val):
            return {}
    except (TypeError, ValueError):
        pass
    s = str(val).strip()
    if not s:
        return {}
    try:
        out = json.loads(s)
        return out if isinstance(out, dict) else {}
    except json.JSONDecodeError:
        return {}


def _decision_answer_rows(decision: dict, *, max_text: int = 500) -> list[dict]:
    """Flatten v0.1 decision ``answers`` for Streamlit (missing → review → safe)."""
    ans = (decision or {}).get("answers") or {}
    if not isinstance(ans, dict):
        return []
    order = {"missing": 0, "review": 1, "safe": 2}
    rows: list[dict] = []
    for k, meta in ans.items():
        if not isinstance(meta, dict):
            continue
        ast = str(meta.get("answer_state") or "")
        text = str(meta.get("text") or "")[:max_text]
        rows.append(
            {
                "field": k,
                "screening_question": CANONICAL_SCREENING_FIELD_LABELS.get(k, k),
                "answer_state": ast,
                "truth_safe": meta.get("truth_safe"),
                "submit_safe": meta.get("submit_safe"),
                "autofill_preview": text,
                "reason_codes": ", ".join(str(x) for x in (meta.get("reason_codes") or [])),
            }
        )
    rows.sort(key=lambda r: (order.get(r["answer_state"], 9), str(r["field"])))
    return rows


def _job_dict_for_application_decision(row: dict) -> dict:
    """Build a job dict for ``build_application_decision`` from a jobs table row."""
    r = dict(row or {})
    url = str(r.get("url") or r.get("applyUrl") or "").strip()
    apply_u = str(r.get("apply_url") or r.get("applyUrl") or "").strip()
    unsup = r.get("unsupported_requirements") or []
    if isinstance(unsup, str):
        try:
            unsup = json.loads(unsup) if unsup.strip().startswith("[") else []
        except json.JSONDecodeError:
            unsup = []
    if not isinstance(unsup, list):
        unsup = []
    return {
        "url": url,
        "apply_url": apply_u or url,
        "title": str(r.get("title") or r.get("position") or r.get("jobTitle") or ""),
        "company": str(r.get("company") or r.get("companyName") or ""),
        "description": str(r.get("description") or "")[:12000],
        "easy_apply_confirmed": bool(r.get("easy_apply_confirmed", False)),
        "fit_decision": str(r.get("fit_decision", "") or ""),
        "ats_score": r.get("ats_score", r.get("final_ats_score")),
        "unsupported_requirements": unsup,
    }


def _streamlit_tracker_user_id() -> str:
    """Tag tracker rows from this UI (override with TRACKER_DEFAULT_USER_ID)."""
    return (os.getenv("TRACKER_DEFAULT_USER_ID") or "streamlit-local").strip()


def _career_api_base_default() -> str:
    return (
        os.getenv("STREAMLIT_CAREER_API_BASE") or os.getenv("CAREER_API_BASE_URL") or "http://127.0.0.1:8000"
    ).rstrip("/")


def _career_api_bearer_default() -> str:
    return (os.getenv("STREAMLIT_CAREER_API_BEARER") or os.getenv("CAREER_API_JWT") or "").strip()


def _career_api_headers(api_key: str, *, bearer: str = "", for_json_body: bool = False) -> dict:
    h: dict = {}
    bt = (bearer or "").strip()
    if bt:
        h["Authorization"] = bt if bt.lower().startswith("bearer ") else f"Bearer {bt}"
    s = (api_key or "").strip()
    if s:
        h["X-API-Key"] = s
    if for_json_body:
        h["Content-Type"] = "application/json"
    return h


def _career_api_call(
    base: str,
    method: str,
    path: str,
    *,
    api_key: str = "",
    bearer: str = "",
    params=None,
    json_body=None,
    extra_headers=None,
    timeout: float = 45.0,
):
    """GET/POST against Career Co-Pilot FastAPI (same routes as MCP parity)."""
    url = f"{base.rstrip('/')}{path}"
    m = method.upper()
    for_json = m in ("POST", "PATCH")
    headers = _career_api_headers(api_key, bearer=bearer, for_json_body=for_json)
    if extra_headers:
        for hk, hv in extra_headers.items():
            if hv is not None and str(hv).strip():
                headers[str(hk)] = str(hv).strip()
    if m == "GET":
        return requests.get(url, headers=headers, params=params or {}, timeout=timeout)
    if m == "POST":
        return requests.post(url, headers=headers, params=params or {}, json=json_body, timeout=timeout)
    if m == "PATCH":
        return requests.patch(url, headers=headers, params=params or {}, json=json_body, timeout=timeout)
    if m == "DELETE":
        return requests.delete(url, headers=headers, params=params or {}, timeout=timeout)
    raise ValueError(f"Unsupported method {method}")


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
    if result.get("truth_safe_ats_ceiling") is not None:
        st.metric("Truth-safe ATS ceiling (est.)", f"{result['truth_safe_ats_ceiling']}%")
        st.caption(result.get("truth_safe_ceiling_reason", ""))
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

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        [
            "📄 Single Job",
            "🚀 Batch URL Processor",
            "🤖 AI Job Finder",
            "🎯 Live ATS Optimizer",
            "💼 My Applications",
            "🔗 ATS / API",
        ]
    )

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
            if sel_for_gen is not None and hasattr(sel_for_gen, "fillna"):
                selected_for_gen = st.session_state.jobs_df[sel_for_gen.fillna(False).astype(bool)]
            else:
                selected_for_gen = pd.DataFrame()
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
                if sel is not None and hasattr(sel, "fillna"):
                    selected_jobs = st.session_state.jobs_df[sel.fillna(False).astype(bool)]
                else:
                    selected_jobs = pd.DataFrame()
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
            if sel is not None and hasattr(sel, "fillna"):
                selected = st.session_state.jobs_df[sel.fillna(False).astype(bool)]
            else:
                selected = pd.DataFrame()
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
                use_llm_preview_export = st.checkbox(
                    "Use LLM for answerer preview (why_role; slower, needs OPENAI_API_KEY)",
                    value=False,
                    key="answerer_preview_use_llm",
                )
                with st.expander("Supervision — application decision (v0.1)", expanded=False):
                    st.caption(
                        "Same contract as MCP **get_application_decision** and REST "
                        "**POST /api/ats/application-decision**. Uses the LLM checkbox above for parity with Recalculate / export."
                    )
                    max_prev = st.number_input(
                        "Max LinkedIn rows to score (selected)",
                        min_value=1,
                        max_value=100,
                        value=25,
                        key="jobfinder_decision_max_rows",
                    )
                    c_clear, _ = st.columns([1, 3])
                    with c_clear:
                        if st.button("Clear decision preview", key="jobfinder_decision_clear"):
                            st.session_state.pop("jobfinder_decision_cache", None)
                            st.rerun()
                    if st.button(
                        "Compute decision preview for selected LinkedIn rows",
                        key="jobfinder_decision_compute",
                    ):
                        master_txt = ""
                        try:
                            if st.session_state.get("base_resume_bytes"):
                                master_txt = extract_text_from_pdf(st.session_state.base_resume_bytes)
                        except Exception:
                            master_txt = ""
                        prof = load_profile()
                        lim = int(max_prev)
                        summaries = []
                        details: list[tuple[str, dict]] = []
                        for i, (_, row) in enumerate(linkedin_jobs.iterrows()):
                            if i >= lim:
                                break
                            j = _df_row_to_plain_dict(row)
                            job = _job_dict_for_application_decision(j)
                            label = f"{str(job.get('company') or '')[:50]} — {str(job.get('title') or '')[:60]}"
                            try:
                                d = build_application_decision(
                                    job,
                                    profile=prof,
                                    master_resume_text=master_txt,
                                    use_llm_preview=use_llm_preview_export,
                                )
                            except Exception as ex:
                                d = {
                                    "schema_version": "0.1",
                                    "job_state": "error",
                                    "safe_to_submit": False,
                                    "policy_reason": str(ex)[:200],
                                    "critical_unsatisfied": [],
                                    "answers": {},
                                    "apply_mode_legacy": "",
                                    "fit_decision": "",
                                    "reasons": [str(ex)[:200]],
                                }
                            summaries.append(
                                {
                                    "company": job.get("company", ""),
                                    "title": (job.get("title") or "")[:80],
                                    "job_state": d.get("job_state"),
                                    "safe_to_submit": d.get("safe_to_submit"),
                                    "apply_mode": d.get("apply_mode_legacy"),
                                    "policy_reason": (d.get("policy_reason") or "")[:100],
                                    "critical_fields": len(d.get("critical_unsatisfied") or []),
                                }
                            )
                            details.append(
                                (
                                    label,
                                    d,
                                    {
                                        "easy_apply_confirmed": bool(
                                            job.get("easy_apply_confirmed", False)
                                        ),
                                        "url": str(
                                            job.get("url") or job.get("apply_url") or ""
                                        ).strip(),
                                    },
                                )
                            )
                        st.session_state["jobfinder_decision_cache"] = {
                            "summaries": summaries,
                            "details": details,
                        }
                    cache = st.session_state.get("jobfinder_decision_cache")
                    if cache and cache.get("summaries"):
                        st.dataframe(
                            pd.DataFrame(cache["summaries"]),
                            hide_index=True,
                            use_container_width=True,
                        )
                        labels = [t[0] for t in cache.get("details") or []]
                        if labels:
                            pick = st.selectbox(
                                "Per-field screening answers",
                                options=list(range(len(labels))),
                                format_func=lambda i: labels[i],
                                key="jobfinder_decision_pick",
                            )
                            _entry = cache["details"][pick]
                            _dec = _entry[1]
                            _meta = (
                                _entry[2]
                                if len(_entry) > 2 and isinstance(_entry[2], dict)
                                else {}
                            )
                            crit = _dec.get("critical_unsatisfied") or []
                            if crit:
                                st.warning("Critical / not submit-safe: " + ", ".join(str(x) for x in crit))
                            js = str(_dec.get("job_state") or "")
                            if js == "safe_auto_apply":
                                st.markdown("##### Safe auto-apply — preconditions")
                                st.caption(
                                    "Operator checklist before CLI/API submit. "
                                    "Prefer **dry_run** or **shadow_mode** first (ATS / REST API tab)."
                                )
                                chk = safe_auto_apply_precondition_checklist(
                                    _dec,
                                    easy_apply_confirmed=bool(
                                        _meta.get("easy_apply_confirmed")
                                    ),
                                )
                                st.dataframe(
                                    pd.DataFrame(chk),
                                    hide_index=True,
                                    use_container_width=True,
                                )
                                u = str(_meta.get("url") or "").strip()
                                if u:
                                    st.caption(f"Job URL: {u}")
                                st.markdown(
                                    """
**Dry run & artifacts**

- **Dry run (no submit):** open the **ATS / REST API** tab → *Batch apply to LinkedIn* → enable **dry_run**.
- **Shadow (fill, no submit):** same section → **shadow_mode** (tracker shows Shadow / would-apply labels).
- **CLI apply:** `scripts/apply_linkedin_jobs.py` — Playwright traces/screenshots depend on your runner flags and cwd (see `scripts/` and `docs/DEPLOY.md`).
                                    """
                                )
                            rows_ans = _decision_answer_rows(_dec, max_text=500)
                            if rows_ans:
                                if js == "manual_assist":
                                    st.markdown("##### Manual assist — screening fields & autofill preview")
                                    st.caption(
                                        "Suggested text is profile/resume grounded (v0.1 answerer). "
                                        "Copy into the employer portal; double-check **review** and **missing** rows."
                                    )
                                    show_all_ma = st.checkbox(
                                        "Show all canonical fields (including safe)",
                                        value=False,
                                        key=f"jobfinder_ma_show_all_{pick}",
                                    )
                                    disp = rows_ans if show_all_ma else [r for r in rows_ans if r.get("answer_state") != "safe"]
                                    if not disp:
                                        st.success("All canonical screening fields are **safe** for autofill.")
                                    else:
                                        st.dataframe(
                                            pd.DataFrame(disp),
                                            hide_index=True,
                                            use_container_width=True,
                                        )
                                        bundle = "\n".join(
                                            f"{r['field']}: {r['autofill_preview']}"
                                            for r in disp
                                            if (r.get("autofill_preview") or "").strip()
                                        )
                                        if bundle.strip():
                                            st.text_area(
                                                "Copy — field → suggested answer",
                                                value=bundle,
                                                height=200,
                                                key=f"jobfinder_ma_copy_{pick}",
                                            )
                                else:
                                    st.caption("Per-field screening (canonical export questions)")
                                    st.dataframe(
                                        pd.DataFrame(rows_ans),
                                        hide_index=True,
                                        use_container_width=True,
                                    )
                            with st.expander("Raw decision JSON"):
                                st.json(_dec)
                if st.button(
                    "Recalculate apply_mode + policy_reason (selected LinkedIn rows)",
                    key="sync_policy_answerer_cols",
                    help="Same canonical answerer preview as JSON export; updates the job table below.",
                ):
                    df = st.session_state.jobs_df.copy()
                    for c, default in (
                        ("policy_reason", ""),
                        ("answerer_manual_review_required", False),
                    ):
                        if c not in df.columns:
                            df[c] = default
                    master_txt = ""
                    try:
                        if st.session_state.get("base_resume_bytes"):
                            master_txt = extract_text_from_pdf(st.session_state.base_resume_bytes)
                    except Exception:
                        pass
                    prof = load_profile()
                    sel = df.get("Select")
                    urls = df["url"].fillna("").astype(str)
                    is_li = urls.str.contains("linkedin.com", na=False)
                    if sel is not None and hasattr(sel, "fillna"):
                        mask = is_li & sel.fillna(False).astype(bool)
                    else:
                        mask = is_li
                    n_up = 0
                    for idx in df[mask].index:
                        j = _df_row_to_plain_dict(df.loc[idx])
                        enriched = enrich_job_dict_for_policy_export(
                            j,
                            profile=prof,
                            master_resume_text=master_txt,
                            use_llm_preview=use_llm_preview_export,
                        )
                        df.at[idx, "apply_mode"] = enriched["apply_mode"]
                        df.at[idx, "policy_reason"] = enriched.get("policy_reason", "")
                        df.at[idx, "answerer_manual_review_required"] = bool(
                            enriched.get("answerer_manual_review_required", False)
                        )
                        n_up += 1
                    st.session_state.jobs_df = df
                    st.success(f"Updated apply_mode / policy_reason for {n_up} LinkedIn row(s).")
                    st.rerun()
                apply_mode_col = linkedin_jobs["apply_mode"] if "apply_mode" in linkedin_jobs.columns else pd.Series(["manual_assist"] * len(linkedin_jobs))
                auto_apply_jobs = linkedin_jobs[apply_mode_col == "auto_easy_apply"] if (apply_mode_col == "auto_easy_apply").any() else pd.DataFrame()
                manual_lane_jobs = linkedin_jobs[apply_mode_col != "auto_easy_apply"]
                if not auto_apply_jobs.empty:
                    st.caption(
                        f"✅ **{len(auto_apply_jobs)}** selected LinkedIn job(s) currently in **auto_easy_apply** lane "
                        "(recalculate button above aligns with profile + answerer preview)."
                    )
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
                    master_txt = ""
                    try:
                        if st.session_state.get("base_resume_bytes"):
                            master_txt = extract_text_from_pdf(st.session_state.base_resume_bytes)
                    except Exception:
                        master_txt = ""
                    prof = load_profile()
                    jobs_export = []
                    for _, row in auto_apply_jobs.iterrows():
                        j = _df_row_to_plain_dict(row)
                        j["applyUrl"] = j.get("url", "")
                        j["easy_apply"] = True
                        j["easy_apply_confirmed"] = True
                        enriched = enrich_job_dict_for_policy_export(
                            j,
                            profile=prof,
                            master_resume_text=master_txt,
                            use_llm_preview=use_llm_preview_export,
                        )
                        thin = {c: enriched.get(c) for c in cols_export if c in enriched}
                        thin["applyUrl"] = enriched.get("applyUrl", enriched.get("url", ""))
                        thin["easy_apply"] = True
                        thin["easy_apply_confirmed"] = bool(enriched.get("easy_apply_confirmed", True))
                        thin["answerer_review"] = enriched.get("answerer_review")
                        thin["answerer_manual_review_required"] = bool(
                            enriched.get("answerer_manual_review_required", False)
                        )
                        thin["apply_mode"] = enriched.get("apply_mode")
                        thin["policy_reason"] = enriched.get("policy_reason", "")
                        jobs_export.append(thin)
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
                    st.caption(
                        "Set LINKEDIN_EMAIL, LINKEDIN_PASSWORD. "
                        "Export uses the same answerer preview as **Recalculate** (see LLM checkbox above)."
                    )
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
        st.checkbox("Auto-apply only on full match", value=True, key="live_auto")

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
                st.caption(
                    "Audit columns (when present): **ats_provider**, **ats_provider_apply_target**, "
                    "**truth_safe_ats_ceiling**, **selected_address_label**, **package_field_stats** — filled on new logs."
                )
                if "application_decision" in display_df.columns:
                    with st.expander("Policy snapshot (logged application_decision)", expanded=False):
                        st.caption("Parsed v0.1 decision JSON from tracker rows when present.")
                        snap_rows = []
                        for _, r in display_df.iterrows():
                            d = _parse_application_decision_cell(r.get("application_decision"))
                            if not d:
                                continue
                            snap_rows.append(
                                {
                                    "company": r.get("Company", r.get("company", "")),
                                    "position": r.get("Position", r.get("position", "")),
                                    "job_state": d.get("job_state"),
                                    "safe_to_submit": d.get("safe_to_submit"),
                                    "policy_reason": (d.get("policy_reason") or "")[:100],
                                }
                            )
                        if snap_rows:
                            st.dataframe(
                                pd.DataFrame(snap_rows),
                                hide_index=True,
                                use_container_width=True,
                            )
                        else:
                            st.info("No parseable application_decision values in loaded rows.")
                if "company" in display_df.columns and "Company" not in display_df.columns:
                    display_df = display_df.rename(columns={"company": "Company", "position": "Position", "status": "Status", "job_description": "Job Description"})
                status_col = "Status" if "Status" in display_df.columns else "status"
                _iv_opts = ["", "none", "scheduled", "completed", "advanced", "rejected", "withdrew", "no_show"]
                _of_opts = ["", "none", "pending", "extended", "accepted", "declined", "ghosted"]
                col_cfg = {
                    status_col: st.column_config.SelectboxColumn(
                        "Status",
                        options=["Applied", "Interviewing", "Offer", "Rejected", "Shadow"],
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
                        sh = tr.get("shadow") or {}
                        if int(sh.get("shadow_rows") or 0) > 0 or int(sh.get("shadow_would_apply_rows") or 0) > 0:
                            st.caption("Phase 2 **shadow** rollups (same tracker scope)")
                            s1, s2, s3 = st.columns(3)
                            s1.metric("Shadow rows", int(sh.get("shadow_rows") or 0))
                            s2.metric("Shadow would apply", int(sh.get("shadow_would_apply_rows") or 0))
                            s3.metric("Applied (submission_status)", int(sh.get("applied_submission_rows") or 0))
                            bss = sh.get("by_shadow_submission") or {}
                            if bss:
                                st.dataframe(
                                    pd.DataFrame(
                                        [{"submission_status": k, "count": v} for k, v in bss.items()]
                                    ),
                                    hide_index=True,
                                    use_container_width=True,
                                )
                        ap = tr.get("by_ats_provider") or {}
                        if ap:
                            st.caption("Top **ats_provider** (listing URL)")
                            ap_df = pd.DataFrame([{"provider": k, "count": v} for k, v in sorted(ap.items(), key=lambda x: -x[1])[:8]])
                            st.dataframe(ap_df, hide_index=True, use_container_width=True)
                        tc = tr.get("truth_safe_ats_ceiling") or {}
                        if tc.get("count_numeric"):
                            st.caption(
                                f"Logged **truth_safe_ats_ceiling**: mean **{tc.get('mean')}** "
                                f"({int(tc.get('count_numeric') or 0)} numeric values)"
                            )
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
                        amat = xtabs.get("apply_mode_by_ats_provider_apply_target") or []
                        if amat:
                            st.caption("Apply mode × apply-target ATS")
                            st.dataframe(pd.DataFrame(amat), hide_index=True, use_container_width=True)
                        subat = xtabs.get("submission_status_by_ats_provider_apply_target") or []
                        if subat:
                            st.caption("Submission status × apply-target ATS")
                            st.dataframe(pd.DataFrame(subat), hide_index=True, use_container_width=True)
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

    with tab6:
        st.header("ATS / REST API")
        st.caption(
            "Optional: call the FastAPI app (uvicorn app.main:app) — same JSON as MCP parity under /api/ats/*. "
            "Set STREAMLIT_CAREER_API_BASE or CAREER_API_BASE_URL for the default base URL."
        )
        api_base = st.text_input("API base URL", value=_career_api_base_default(), key="career_api_base_url")
        api_key_ui = st.text_input("X-API-Key (if server requires it)", type="password", key="career_api_key_ui")
        api_bearer_ui = st.text_input(
            "Bearer JWT (optional; Authorization header — checked before API key on server)",
            value=_career_api_bearer_default(),
            type="password",
            key="career_api_bearer_ui",
        )

        def _call(method: str, path: str, **kwargs):
            return _career_api_call(
                api_base,
                method,
                path,
                api_key=api_key_ui,
                bearer=api_bearer_ui,
                **kwargs,
            )

        def _show_api_response(resp: requests.Response) -> None:
            st.caption(f"HTTP {resp.status_code}")
            try:
                data = resp.json()
            except Exception:
                st.code((resp.text or "")[:4000] or "(empty body)")
                return
            if isinstance(data, (dict, list)):
                st.json(data)
            else:
                st.write(data)

        with st.expander("Service health", expanded=True):
            st.caption("Root paths (no `/api` prefix). `/metrics` is Prometheus text when `PROMETHEUS_METRICS=1` and metrics extras are installed.")
            r1c1, r1c2 = st.columns(2)
            with r1c1:
                if st.button("GET /health", key="career_api_btn_health"):
                    try:
                        r = _call("GET", "/health", timeout=15.0)
                        _show_api_response(r)
                    except requests.RequestException as ex:
                        st.error(f"Connection error: {ex}")
            with r1c2:
                if st.button("GET /ready", key="career_api_btn_ready"):
                    try:
                        r = _call("GET", "/ready", timeout=15.0)
                        _show_api_response(r)
                    except requests.RequestException as ex:
                        st.error(f"Connection error: {ex}")
            r2c1, r2c2 = st.columns(2)
            with r2c1:
                if st.button("GET /", key="career_api_btn_root"):
                    try:
                        r = _call("GET", "/", timeout=15.0)
                        _show_api_response(r)
                    except requests.RequestException as ex:
                        st.error(f"Connection error: {ex}")
            with r2c2:
                if st.button("GET /metrics", key="career_api_btn_metrics"):
                    try:
                        r = _call("GET", "/metrics", timeout=15.0)
                        _show_api_response(r)
                    except requests.RequestException as ex:
                        st.error(f"Connection error: {ex}")

        with st.expander("ATS metadata", expanded=False):
            plat_job = st.text_input("Platform: job_url", value="https://www.linkedin.com/jobs/view/1", key="api_plat_job")
            plat_apply = st.text_input("Platform: apply_url", value="", key="api_plat_apply")
            if st.button("GET /api/ats/platform", key="api_plat_btn"):
                try:
                    r = _call(
                        "GET",
                        "/api/ats/platform",
                        params={"job_url": plat_job.strip(), "apply_url": plat_apply.strip()},
                        timeout=30.0,
                    )
                    _show_api_response(r)
                except requests.RequestException as ex:
                    st.error(f"Connection error: {ex}")

            ft_url = st.text_input("Form type: URL", value="https://www.linkedin.com/jobs/view/1", key="api_ft_url")
            if st.button("GET /api/ats/form-type", key="api_ft_btn"):
                try:
                    r = _call(
                        "GET",
                        "/api/ats/form-type",
                        params={"url": ft_url.strip()},
                        timeout=30.0,
                    )
                    _show_api_response(r)
                except requests.RequestException as ex:
                    st.error(f"Connection error: {ex}")

        with st.expander("Profile & autofill", expanded=False):
            prof_path = st.text_input("validate-profile: profile_path (optional)", value="", key="api_vprof_path")
            if st.button("POST /api/ats/validate-profile", key="api_vprof_btn"):
                try:
                    r = _call(
                        "POST",
                        "/api/ats/validate-profile",
                        json_body={"profile_path": prof_path.strip()},
                        timeout=30.0,
                    )
                    _show_api_response(r)
                except requests.RequestException as ex:
                    st.error(f"Connection error: {ex}")

            af_type = st.selectbox("autofill: form_type", ["linkedin", "greenhouse", "lever", "workday", "generic"], key="api_af_type")
            af_hints = st.text_input("autofill: question_hints (comma-separated)", value="sponsorship", key="api_af_hints")
            if st.button("POST /api/ats/autofill-values", key="api_af_btn"):
                try:
                    r = _call(
                        "POST",
                        "/api/ats/autofill-values",
                        json_body={"form_type": af_type, "question_hints": af_hints},
                        timeout=30.0,
                    )
                    _show_api_response(r)
                except requests.RequestException as ex:
                    st.error(f"Connection error: {ex}")

        with st.expander("Apply policy (JSON job)", expanded=False):
            st.caption("POST /api/ats/decide-apply-mode — edit the job object if needed.")
            dam_json = st.text_area(
                "Request JSON",
                value=json.dumps(
                    {
                        "job": {
                            "url": "https://www.linkedin.com/jobs/view/1/",
                            "easy_apply_confirmed": True,
                        },
                        "fit_decision": "apply",
                        "ats_score": 90,
                        "unsupported_requirements": [],
                    },
                    indent=2,
                ),
                height=220,
                key="api_dam_json",
            )
            if st.button("POST /api/ats/decide-apply-mode", key="api_dam_btn"):
                try:
                    body = json.loads(dam_json)
                except json.JSONDecodeError as je:
                    st.error(f"Invalid JSON: {je}")
                else:
                    try:
                        r = _call(
                            "POST",
                            "/api/ats/decide-apply-mode",
                            json_body=body,
                            timeout=30.0,
                        )
                        _show_api_response(r)
                    except requests.RequestException as ex:
                        st.error(f"Connection error: {ex}")

        with st.expander("Application decision v0.1 (job_state, safe_to_submit)", expanded=False):
            st.caption("POST /api/ats/application-decision — same payload as MCP get_application_decision.")
            ad_json = st.text_area(
                "Request JSON",
                value=json.dumps(
                    {
                        "job": {
                            "url": "https://www.linkedin.com/jobs/view/1/",
                            "easy_apply_confirmed": True,
                            "fit_decision": "apply",
                            "ats_score": 90,
                            "unsupported_requirements": [],
                            "title": "MLE",
                            "company": "ACME",
                            "description": "Python ML role.",
                        },
                        "profile_path": "",
                        "master_resume_text": "",
                        "blocked_reason": "",
                    },
                    indent=2,
                ),
                height=260,
                key="api_adec_json",
            )
            if st.button("POST /api/ats/application-decision", key="api_adec_btn"):
                try:
                    body = json.loads(ad_json)
                except json.JSONDecodeError as je:
                    st.error(f"Invalid JSON: {je}")
                else:
                    try:
                        r = _call(
                            "POST",
                            "/api/ats/application-decision",
                            json_body=body,
                            timeout=60.0,
                        )
                        _show_api_response(r)
                    except requests.RequestException as ex:
                        st.error(f"Connection error: {ex}")

        with st.expander("LinkedIn batch apply (browser API)", expanded=False):
            st.caption(
                "POST /api/ats/apply-to-jobs — runs on the **API server** (needs `ATS_ALLOW_LINKEDIN_BROWSER=1`, "
                "Playwright, LinkedIn credentials). Use **shadow_mode** for Phase 2 (fill, no submit). "
                "Phase 3: add `pilot_submit_allowed: true` on jobs when `AUTONOMY_LINKEDIN_PILOT_SUBMIT_ONLY=1`. "
                "Max 50 jobs per request."
            )
            baj_jobs = st.text_area(
                "jobs (JSON array)",
                height=180,
                key="api_baj_jobs",
                value=json.dumps(
                    [
                        {
                            "title": "Engineer",
                            "company": "ACME",
                            "url": "https://www.linkedin.com/jobs/view/1234567890/",
                            "easy_apply_confirmed": True,
                            "apply_mode": "auto_easy_apply",
                            "fit_decision": "apply",
                            "ats_score": 90,
                            "unsupported_requirements": [],
                        }
                    ],
                    indent=2,
                ),
            )
            baj_dry = st.checkbox("dry_run", value=False, key="api_baj_dry")
            baj_shadow = st.checkbox(
                "shadow_mode (Phase 2 — no submit; Shadow – Would Apply / Not Apply in tracker)",
                value=False,
                key="api_baj_shadow",
            )
            baj_safe = st.checkbox("require_safeguards", value=True, key="api_baj_safe")
            baj_rl = st.number_input("rate_limit_seconds", min_value=5.0, max_value=600.0, value=90.0, key="api_baj_rl")
            if st.button("POST /api/ats/apply-to-jobs", key="api_baj_btn"):
                try:
                    jobs_parsed = json.loads(baj_jobs)
                except json.JSONDecodeError as je:
                    st.error(f"Invalid jobs JSON: {je}")
                else:
                    if not isinstance(jobs_parsed, list):
                        st.error("jobs must be a JSON array")
                    else:
                        try:
                            r = _call(
                                "POST",
                                "/api/ats/apply-to-jobs",
                                json_body={
                                    "jobs": jobs_parsed,
                                    "dry_run": baj_dry,
                                    "shadow_mode": baj_shadow,
                                    "require_safeguards": baj_safe,
                                    "rate_limit_seconds": float(baj_rl),
                                },
                                timeout=600.0,
                            )
                            _show_api_response(r)
                        except requests.RequestException as ex:
                            st.error(f"Connection error: {ex}")

        with st.expander("Score job fit, address, static analyze-form", expanded=False):
            st.caption("POST /api/ats/score-job-fit — JD + resume text required (min length enforced by API).")
            sjf_use_pdf = st.checkbox(
                "Use sidebar-uploaded resume PDF as master_resume_text",
                key="api_sjf_use_pdf",
            )
            sjf_jd = st.text_area("job_description", height=140, key="api_sjf_jd", placeholder="Paste job description…")
            sjf_resume = st.text_area(
                "master_resume_text (ignored if PDF checkbox above is on and resume is uploaded)",
                height=140,
                key="api_sjf_resume",
                placeholder="Paste resume text…",
            )
            cj, ck = st.columns(2)
            sjf_title = cj.text_input("job_title", value="Engineer", key="api_sjf_title")
            sjf_co = ck.text_input("company", value="ACME", key="api_sjf_co")
            sjf_loc = st.text_input("location", value="USA", key="api_sjf_loc")
            if st.button("POST /api/ats/score-job-fit", key="api_sjf_btn"):
                resume_body = sjf_resume
                if sjf_use_pdf and st.session_state.get("base_resume_bytes"):
                    resume_body = extract_text_from_pdf(st.session_state["base_resume_bytes"])
                if not (sjf_jd or "").strip() or not (resume_body or "").strip():
                    st.error("Provide job_description and resume text (or enable PDF + upload in sidebar).")
                else:
                    try:
                        r = _call(
                            "POST",
                            "/api/ats/score-job-fit",
                            json_body={
                                "job_description": sjf_jd,
                                "master_resume_text": resume_body,
                                "job_title": sjf_title,
                                "company": sjf_co,
                                "location": sjf_loc,
                            },
                            timeout=120.0,
                        )
                        _show_api_response(r)
                    except requests.RequestException as ex:
                        st.error(f"Connection error: {ex}")

            st.divider()
            st.caption("POST /api/ats/address-for-job — uses server candidate profile.")
            ad_loc = st.text_input("address: job_location", value="Remote", key="api_ad_loc")
            ad_title = st.text_input("address: job_title", value="Engineer", key="api_ad_title")
            ad_jd = st.text_area("address: job_description (optional)", height=80, key="api_ad_jd")
            ad_wt = st.text_input("address: work_type (optional)", value="", key="api_ad_wt")
            if st.button("POST /api/ats/address-for-job", key="api_ad_btn"):
                try:
                    r = _call(
                        "POST",
                        "/api/ats/address-for-job",
                        json_body={
                            "job_location": ad_loc,
                            "job_title": ad_title,
                            "job_description": ad_jd,
                            "work_type": ad_wt,
                        },
                        timeout=45.0,
                    )
                    _show_api_response(r)
                except requests.RequestException as ex:
                    st.error(f"Connection error: {ex}")

            st.divider()
            st.caption("POST /api/ats/analyze-form — static hints only (no browser).")
            an_job = st.text_input("analyze-form: job_url", value="https://boards.greenhouse.io/example/jobs/1", key="api_an_job")
            an_apply = st.text_input("analyze-form: apply_url", value="", key="api_an_apply")
            if st.button("POST /api/ats/analyze-form", key="api_an_btn"):
                try:
                    r = _call(
                        "POST",
                        "/api/ats/analyze-form",
                        json_body={"job_url": an_job.strip(), "apply_url": an_apply.strip()},
                        timeout=45.0,
                    )
                    _show_api_response(r)
                except requests.RequestException as ex:
                    st.error(f"Connection error: {ex}")

        with st.expander("Search jobs (LinkedIn MCP bridge)", expanded=False):
            st.caption("POST /api/ats/search-jobs — needs linkedin-mcp-server; may hit API_RATE_LIMIT_ATS_SEARCH_JOBS_PER_MINUTE.")
            sj_kw = st.text_input("keywords", value="machine learning engineer", key="api_sj_kw")
            sj_loc = st.text_input("location", value="United States", key="api_sj_loc")
            sj_wt = st.text_input("work_type", value="remote", key="api_sj_wt")
            sj_max = st.number_input("max_results", min_value=1, max_value=100, value=10, key="api_sj_max")
            sj_ez = st.checkbox("easy_apply", value=False, key="api_sj_ez")
            if st.button("POST /api/ats/search-jobs", key="api_sj_btn"):
                try:
                    r = _call(
                        "POST",
                        "/api/ats/search-jobs",
                        json_body={
                            "keywords": sj_kw,
                            "location": sj_loc,
                            "work_type": sj_wt,
                            "max_results": int(sj_max),
                            "easy_apply": sj_ez,
                        },
                        timeout=90.0,
                    )
                    _show_api_response(r)
                except requests.RequestException as ex:
                    st.error(f"Connection error: {ex}")

        with st.expander("Truth inventory & resume / package prep", expanded=False):
            st.caption("POST /api/ats/truth-inventory — inline text (100+ chars) or project-relative master_resume_path on server.")
            ti_text = st.text_area("master_resume_text (optional)", height=100, key="api_ti_text")
            ti_path = st.text_input("master_resume_path (optional, project-relative)", value="", key="api_ti_path")
            if st.button("POST /api/ats/truth-inventory", key="api_ti_btn"):
                try:
                    r = _call(
                        "POST",
                        "/api/ats/truth-inventory",
                        json_body={"master_resume_text": ti_text, "master_resume_path": ti_path.strip()},
                        timeout=60.0,
                    )
                    _show_api_response(r)
                except requests.RequestException as ex:
                    st.error(f"Connection error: {ex}")

            st.divider()
            pr_title = st.text_input("prepare-resume: job_title", value="ML Engineer", key="api_pr_title")
            pr_co = st.text_input("prepare-resume: company", value="ACME", key="api_pr_co")
            pr_src = st.text_input("prepare-resume: resume_source_path (optional)", value="", key="api_pr_src")
            if st.button("POST /api/ats/prepare-resume-for-job", key="api_pr_btn"):
                try:
                    r = _call(
                        "POST",
                        "/api/ats/prepare-resume-for-job",
                        json_body={
                            "job_title": pr_title,
                            "company": pr_co,
                            "resume_source_path": pr_src.strip(),
                        },
                        timeout=60.0,
                    )
                    _show_api_response(r)
                except requests.RequestException as ex:
                    st.error(f"Connection error: {ex}")

            st.divider()
            st.caption("POST /api/ats/prepare-application-package — server profile + answerer; optional fit if JD + resume below.")
            pp_use = st.checkbox("Use uploaded PDF for master_resume_text", key="api_pp_use_pdf")
            pp_jt = st.text_input("package: job_title", value="Engineer", key="api_pp_jt")
            pp_co = st.text_input("package: company", value="ACME", key="api_pp_co")
            pp_jd = st.text_area("package: job_description", height=100, key="api_pp_jd")
            pp_res = st.text_area("package: master_resume_text (if not using PDF)", height=100, key="api_pp_res")
            pp_jloc = st.text_input("package: job_location", value="", key="api_pp_jloc")
            pp_wt = st.text_input("package: work_type", value="", key="api_pp_wt")
            if st.button("POST /api/ats/prepare-application-package", key="api_pp_btn"):
                mt = pp_res
                if pp_use and st.session_state.get("base_resume_bytes"):
                    mt = extract_text_from_pdf(st.session_state["base_resume_bytes"])
                try:
                    r = _call(
                        "POST",
                        "/api/ats/prepare-application-package",
                        json_body={
                            "job_title": pp_jt,
                            "company": pp_co,
                            "job_description": pp_jd,
                            "master_resume_text": mt,
                            "job_location": pp_jloc,
                            "work_type": pp_wt,
                        },
                        timeout=120.0,
                    )
                    _show_api_response(r)
                except requests.RequestException as ex:
                    st.error(f"Connection error: {ex}")

        with st.expander("Batch prioritize & run-result reports", expanded=False):
            st.caption("POST /api/ats/batch-prioritize-jobs — max 500 jobs in API; max_scored ≤ 200.")
            bp_jobs = st.text_area(
                "jobs (JSON array of job objects with description, url, …)",
                height=160,
                key="api_bp_jobs",
                value='[\n  {\n    "title": "Engineer",\n    "company": "ACME",\n    "description": "'
                + ("Senior Python engineer with AWS kubernetes docker. " * 8)
                + '",\n    "url": "https://example.com/j",\n    "easy_apply_confirmed": true\n  }\n]',
            )
            bp_use_pdf = st.checkbox("Use uploaded PDF text as master_resume_text", key="api_bp_use_pdf")
            bp_resume = st.text_area("master_resume_text (if not using PDF)", height=100, key="api_bp_res")
            bp_max = st.number_input("max_scored", min_value=1, max_value=200, value=20, key="api_bp_max")
            if st.button("POST /api/ats/batch-prioritize-jobs", key="api_bp_btn"):
                try:
                    jobs_parsed = json.loads(bp_jobs)
                except json.JSONDecodeError as je:
                    st.error(f"Invalid jobs JSON: {je}")
                else:
                    mrt = bp_resume
                    if bp_use_pdf and st.session_state.get("base_resume_bytes"):
                        mrt = extract_text_from_pdf(st.session_state["base_resume_bytes"])
                    if not (mrt or "").strip():
                        st.error("Provide master_resume_text or enable PDF + sidebar upload.")
                    else:
                        try:
                            r = _call(
                                "POST",
                                "/api/ats/batch-prioritize-jobs",
                                json_body={"jobs": jobs_parsed, "master_resume_text": mrt, "max_scored": int(bp_max)},
                                timeout=180.0,
                            )
                            _show_api_response(r)
                        except requests.RequestException as ex:
                            st.error(f"Connection error: {ex}")

            st.divider()
            rr_json = st.text_area(
                "run_results JSON (array of run row dicts)",
                height=140,
                key="api_rr_json",
                value='[{"status":"applied","unmapped_fields":["Salary"],"error":""}]',
            )
            c_ru, c_au = st.columns(2)
            with c_ru:
                if st.button("POST /api/ats/review-unmapped-fields", key="api_rr_unmapped"):
                    try:
                        rows = json.loads(rr_json)
                        r = _call(
                            "POST",
                            "/api/ats/review-unmapped-fields",
                            json_body={"run_results": rows},
                            timeout=45.0,
                        )
                        _show_api_response(r)
                    except json.JSONDecodeError as je:
                        st.error(f"Invalid JSON: {je}")
                    except requests.RequestException as ex:
                        st.error(f"Connection error: {ex}")
            with c_au:
                if st.button("POST /api/ats/application-audit-report", key="api_rr_audit"):
                    try:
                        rows = json.loads(rr_json)
                        r = _call(
                            "POST",
                            "/api/ats/application-audit-report",
                            json_body={"run_results": rows},
                            timeout=45.0,
                        )
                        _show_api_response(r)
                    except json.JSONDecodeError as je:
                        st.error(f"Invalid JSON: {je}")
                    except requests.RequestException as ex:
                        st.error(f"Connection error: {ex}")

        with st.expander("Recruiter follow-up (OpenAI on server)", expanded=False):
            st.caption("POST /api/ats/generate-recruiter-followup — API server needs OPENAI_API_KEY.")
            rf_t = st.text_input("job_title", value="PM", key="api_rf_t")
            rf_c = st.text_input("company", value="ACME", key="api_rf_c")
            rf_d = st.text_input("application_date (optional)", value="", key="api_rf_d")
            if st.button("POST /api/ats/generate-recruiter-followup", key="api_rf_btn"):
                try:
                    r = _call(
                        "POST",
                        "/api/ats/generate-recruiter-followup",
                        json_body={"job_title": rf_t, "company": rf_c, "application_date": rf_d},
                        timeout=90.0,
                    )
                    _show_api_response(r)
                except requests.RequestException as ex:
                    st.error(f"Connection error: {ex}")

        with st.expander("Live form probe (optional)", expanded=False):
            st.caption(
                "POST /api/ats/analyze-form/live — set ATS_ALLOW_LIVE_FORM_PROBE=1 on the API; 403 if disabled."
            )
            lv_apply = st.text_input("apply_url (or job_url)", value="", key="api_lv_apply", placeholder="https://…")
            lv_job = st.text_input("job_url (optional)", value="", key="api_lv_job")
            lv_max = st.number_input("max_fields", min_value=5, max_value=80, value=30, key="api_lv_max")
            if st.button("POST /api/ats/analyze-form/live", key="api_lv_btn"):
                try:
                    r = _call(
                        "POST",
                        "/api/ats/analyze-form/live",
                        json_body={
                            "apply_url": lv_apply.strip(),
                            "job_url": lv_job.strip(),
                            "max_fields": int(lv_max),
                        },
                        timeout=60.0,
                    )
                    _show_api_response(r)
                except requests.RequestException as ex:
                    st.error(f"Connection error: {ex}")

        with st.expander("Authenticated routes (JWT or X-API-Key)", expanded=False):
            st.caption(
                "Uses the Bearer / X-API-Key fields at the top of this tab. "
                "If the server sets API_KEY, you must send a matching key or valid JWT. "
                "If API_KEY is unset, requests run as demo-user."
            )
            if st.button("GET /api/applications", key="api_auth_apps"):
                try:
                    r = _call("GET", "/api/applications", timeout=30.0)
                    _show_api_response(r)
                except requests.RequestException as ex:
                    st.error(f"Connection error: {ex}")

            fu_due = st.checkbox("follow-ups: due_only", value=True, key="api_fu_due")
            fu_lim = st.number_input("follow-ups: limit", 1, 200, 50, key="api_fu_lim")
            if st.button("GET /api/follow-ups", key="api_fu_btn"):
                try:
                    r = _call(
                        "GET",
                        "/api/follow-ups",
                        params={
                            "due_only": fu_due,
                            "include_snoozed": True,
                            "limit": int(fu_lim),
                            "sort_by_priority": True,
                        },
                        timeout=30.0,
                    )
                    _show_api_response(r)
                except requests.RequestException as ex:
                    st.error(f"Connection error: {ex}")

            in_aud = st.checkbox("insights: include_audit", value=True, key="api_ins_aud")
            in_max = st.number_input("insights: audit_max_lines", 100, 20000, 2500, key="api_ins_max")
            if st.button("GET /api/insights", key="api_ins_btn"):
                try:
                    r = _call(
                        "GET",
                        "/api/insights",
                        params={"include_audit": in_aud, "audit_max_lines": int(in_max)},
                        timeout=60.0,
                    )
                    _show_api_response(r)
                except requests.RequestException as ex:
                    st.error(f"Connection error: {ex}")

            abj_id = st.text_input(
                "applications/by-job: job_id (external id from tracker)",
                value="",
                key="api_abj_id",
                placeholder="e.g. linkedin job id",
            )
            if st.button("GET /api/applications/by-job/{job_id}", key="api_abj_btn"):
                if not (abj_id or "").strip():
                    st.error("Enter job_id")
                else:
                    try:
                        path = f"/api/applications/by-job/{quote(abj_id.strip(), safe='')}"
                        r = _call("GET", path, timeout=30.0)
                        _show_api_response(r)
                    except requests.RequestException as ex:
                        st.error(f"Connection error: {ex}")

            st.divider()
            st.caption("GET /api/follow-ups/digest — due-only digest with plain `text` plus structured `items`.")
            dig_sn = st.checkbox("digest: include_snoozed", value=True, key="api_dig_sn")
            dig_lim = st.number_input("digest: limit", 1, 100, 30, key="api_dig_lim")
            if st.button("GET /api/follow-ups/digest", key="api_dig_btn"):
                try:
                    r = _call(
                        "GET",
                        "/api/follow-ups/digest",
                        params={
                            "include_snoozed": dig_sn,
                            "limit": int(dig_lim),
                            "sort_by_priority": True,
                        },
                        timeout=45.0,
                    )
                    _show_api_response(r)
                except requests.RequestException as ex:
                    st.error(f"Connection error: {ex}")

            st.divider()
            st.caption("POST /api/jobs — enqueue a Celery background job (returns 202 + job_id).")
            job_body = st.text_area(
                "Request JSON (name, payload, optional idempotency_key in body)",
                height=180,
                key="api_job_post_json",
                value=json.dumps({"name": "streamlit-api-test", "payload": {}}, indent=2),
            )
            idem_h = st.text_input(
                "Idempotency-Key header (optional; if body also has idempotency_key they must match)",
                value="",
                key="api_job_idem",
            )
            if st.button("POST /api/jobs", key="api_job_post_btn"):
                try:
                    body = json.loads(job_body)
                except json.JSONDecodeError as je:
                    st.error(f"Invalid JSON: {je}")
                else:
                    extra = {}
                    if (idem_h or "").strip():
                        extra["Idempotency-Key"] = idem_h.strip()
                    try:
                        r = _call(
                            "POST",
                            "/api/jobs",
                            json_body=body,
                            extra_headers=extra if extra else None,
                            timeout=30.0,
                        )
                        _show_api_response(r)
                    except requests.RequestException as ex:
                        st.error(f"Connection error: {ex}")

            st.divider()
            st.caption("GET /api/jobs/{job_id} — poll Celery status (optional result / task_state).")
            gj_id = st.text_input("jobs: job_id (UUID from POST /api/jobs)", value="", key="api_gj_id")
            gj_res = st.checkbox("jobs: include_result", value=False, key="api_gj_res")
            gj_ts = st.checkbox("jobs: include_task_state", value=False, key="api_gj_ts")
            if st.button("GET /api/jobs/{job_id}", key="api_gj_btn"):
                if not (gj_id or "").strip():
                    st.error("Enter job_id")
                else:
                    try:
                        path = f"/api/jobs/{quote(gj_id.strip(), safe='')}"
                        r = _call(
                            "GET",
                            path,
                            params={"include_result": gj_res, "include_task_state": gj_ts},
                            timeout=30.0,
                        )
                        _show_api_response(r)
                    except requests.RequestException as ex:
                        st.error(f"Connection error: {ex}")

            st.divider()
            st.caption(
                "PATCH tracker row by internal **id** (from GET /api/applications → items[].id), not external job_id."
            )
            p_app = st.text_input("applications/{id}: application_id (row id)", value="", key="api_patch_app_id")
            fu_patch_json = st.text_area(
                "PATCH …/follow-up JSON (follow_up_at ISO, follow_up_status, follow_up_note)",
                height=120,
                key="api_fu_patch_json",
                value=json.dumps(
                    {
                        "follow_up_status": "pending",
                        "follow_up_note": "Reminder set from Streamlit API tab",
                    },
                    indent=2,
                ),
            )
            if st.button("PATCH /api/applications/{id}/follow-up", key="api_fu_patch_btn"):
                if not (p_app or "").strip():
                    st.error("Enter application_id (tracker row id)")
                else:
                    try:
                        body = json.loads(fu_patch_json)
                    except json.JSONDecodeError as je:
                        st.error(f"Invalid JSON: {je}")
                    else:
                        try:
                            path = f"/api/applications/{quote(p_app.strip(), safe='')}/follow-up"
                            r = _call("PATCH", path, json_body=body, timeout=30.0)
                            _show_api_response(r)
                        except requests.RequestException as ex:
                            st.error(f"Connection error: {ex}")

            pipe_patch_json = st.text_area(
                "PATCH …/pipeline JSON (interview_stage, offer_outcome)",
                height=100,
                key="api_pipe_patch_json",
                value=json.dumps({"interview_stage": "scheduled", "offer_outcome": ""}, indent=2),
            )
            if st.button("PATCH /api/applications/{id}/pipeline", key="api_pipe_patch_btn"):
                if not (p_app or "").strip():
                    st.error("Enter application_id (tracker row id)")
                else:
                    try:
                        body = json.loads(pipe_patch_json)
                    except json.JSONDecodeError as je:
                        st.error(f"Invalid JSON: {je}")
                    else:
                        try:
                            path = f"/api/applications/{quote(p_app.strip(), safe='')}/pipeline"
                            r = _call("PATCH", path, json_body=body, timeout=30.0)
                            _show_api_response(r)
                        except requests.RequestException as ex:
                            st.error(f"Connection error: {ex}")

            with st.expander("Admin routes (JWT / API key with admin role)", expanded=False):
                st.caption(
                    "Returns **403** unless the principal is admin (JWT role in JWT_ADMIN_ROLES, "
                    "API_KEY_IS_ADMIN=1, or DEMO_USER_IS_ADMIN=1 for demo-user)."
                )
                if st.button("GET /api/admin/applications", key="api_adm_apps"):
                    try:
                        r = _call("GET", "/api/admin/applications", timeout=45.0)
                        _show_api_response(r)
                    except requests.RequestException as ex:
                        st.error(f"Connection error: {ex}")

                adm_ins_aud = st.checkbox("admin insights: include_audit", value=True, key="api_adm_ins_aud")
                adm_ins_max = st.number_input(
                    "admin insights: audit_max_lines", 100, 50000, 5000, key="api_adm_ins_max"
                )
                if st.button("GET /api/admin/insights", key="api_adm_ins"):
                    try:
                        r = _call(
                            "GET",
                            "/api/admin/insights",
                            params={"include_audit": adm_ins_aud, "audit_max_lines": int(adm_ins_max)},
                            timeout=90.0,
                        )
                        _show_api_response(r)
                    except requests.RequestException as ex:
                        st.error(f"Connection error: {ex}")

                if st.button("GET /api/admin/metrics/summary", key="api_adm_met"):
                    try:
                        r = _call("GET", "/api/admin/metrics/summary", timeout=20.0)
                        _show_api_response(r)
                    except requests.RequestException as ex:
                        st.error(f"Connection error: {ex}")

                adm_celery_insp_to = st.number_input(
                    "Celery inspect: timeout (s)", 0.5, 30.0, 2.0, step=0.5, key="api_adm_cel_insp_to"
                )
                if st.button("GET /api/admin/celery/inspect", key="api_adm_cel_insp"):
                    try:
                        r = _call(
                            "GET",
                            "/api/admin/celery/inspect",
                            params={"timeout": float(adm_celery_insp_to)},
                            timeout=min(45.0, float(adm_celery_insp_to) + 5.0),
                        )
                        _show_api_response(r)
                    except requests.RequestException as ex:
                        st.error(f"Connection error: {ex}")

                st.divider()
                st.caption(
                    "PII export / delete (Phase 4.4.2) — **destructive** delete requires matching confirm field."
                )
                adm_pii_uid = st.text_input("admin PII: user_id to export or delete", value="", key="api_adm_pii_uid")
                adm_pii_lim = st.number_input("admin export: limit", 1, 20000, 5000, key="api_adm_pii_lim")
                if st.button("GET /api/admin/applications/export", key="api_adm_pii_exp"):
                    if not (adm_pii_uid or "").strip():
                        st.error("Enter user_id")
                    else:
                        try:
                            r = _call(
                                "GET",
                                "/api/admin/applications/export",
                                params={"user_id": adm_pii_uid.strip(), "limit": int(adm_pii_lim)},
                                timeout=120.0,
                            )
                            _show_api_response(r)
                        except requests.RequestException as ex:
                            st.error(f"Connection error: {ex}")
                adm_pii_confirm = st.text_input(
                    "admin delete: type same user_id to confirm",
                    value="",
                    key="api_adm_pii_conf",
                )
                if st.button("DELETE /api/admin/applications/by-user", key="api_adm_pii_del"):
                    uid = (adm_pii_uid or "").strip()
                    if not uid:
                        st.error("Enter user_id above")
                    elif (adm_pii_confirm or "").strip() != uid:
                        st.error("Confirm field must match user_id exactly")
                    else:
                        try:
                            r = _call(
                                "DELETE",
                                "/api/admin/applications/by-user",
                                params={"user_id": uid, "confirm_user_id": uid},
                                timeout=60.0,
                            )
                            _show_api_response(r)
                        except requests.RequestException as ex:
                            st.error(f"Connection error: {ex}")

                adm_fu_due = st.checkbox("admin follow-ups: due_only", value=True, key="api_adm_fu_due")
                adm_fu_sn = st.checkbox("admin follow-ups: include_snoozed", value=True, key="api_adm_fu_sn")
                adm_fu_lim = st.number_input("admin follow-ups: limit", 1, 500, 100, key="api_adm_fu_lim")
                if st.button("GET /api/admin/follow-ups", key="api_adm_fu"):
                    try:
                        r = _call(
                            "GET",
                            "/api/admin/follow-ups",
                            params={
                                "due_only": adm_fu_due,
                                "include_snoozed": adm_fu_sn,
                                "limit": int(adm_fu_lim),
                                "sort_by_priority": True,
                            },
                            timeout=45.0,
                        )
                        _show_api_response(r)
                    except requests.RequestException as ex:
                        st.error(f"Connection error: {ex}")

                adm_dig_lim = st.number_input("admin digest: limit", 1, 200, 50, key="api_adm_dig_lim")
                adm_dig_sn = st.checkbox("admin digest: include_snoozed", value=True, key="api_adm_dig_sn")
                if st.button("GET /api/admin/follow-ups/digest", key="api_adm_dig"):
                    try:
                        r = _call(
                            "GET",
                            "/api/admin/follow-ups/digest",
                            params={
                                "include_snoozed": adm_dig_sn,
                                "limit": int(adm_dig_lim),
                                "sort_by_priority": True,
                            },
                            timeout=45.0,
                        )
                        _show_api_response(r)
                    except requests.RequestException as ex:
                        st.error(f"Connection error: {ex}")

                adm_abj = st.text_input(
                    "admin applications/by-job: job_id (any user)",
                    value="",
                    key="api_adm_abj",
                    placeholder="external job id",
                )
                adm_abj_su = st.checkbox("admin by-job: signed_urls", value=False, key="api_adm_abj_su")
                if st.button("GET /api/admin/applications/by-job/{job_id}", key="api_adm_abj_btn"):
                    if not (adm_abj or "").strip():
                        st.error("Enter job_id")
                    else:
                        try:
                            path = f"/api/admin/applications/by-job/{quote(adm_abj.strip(), safe='')}"
                            r = _call(
                                "GET",
                                path,
                                params={"signed_urls": adm_abj_su},
                                timeout=30.0,
                            )
                            _show_api_response(r)
                        except requests.RequestException as ex:
                            st.error(f"Connection error: {ex}")

                st.divider()
                st.caption(
                    "PATCH admin — same bodies as user PATCH; updates **any** row by internal id (no user scope)."
                )
                adm_patch_id = st.text_input(
                    "admin PATCH: application_id (row id)",
                    value="",
                    key="api_adm_patch_id",
                )
                adm_fu_pjson = st.text_area(
                    "admin PATCH …/follow-up JSON",
                    height=100,
                    key="api_adm_fu_pjson",
                    value=json.dumps(
                        {"follow_up_status": "pending", "follow_up_note": "Admin update via Streamlit"},
                        indent=2,
                    ),
                )
                if st.button("PATCH /api/admin/applications/{id}/follow-up", key="api_adm_fu_patch"):
                    if not (adm_patch_id or "").strip():
                        st.error("Enter application_id")
                    else:
                        try:
                            body = json.loads(adm_fu_pjson)
                        except json.JSONDecodeError as je:
                            st.error(f"Invalid JSON: {je}")
                        else:
                            try:
                                path = f"/api/admin/applications/{quote(adm_patch_id.strip(), safe='')}/follow-up"
                                r = _call("PATCH", path, json_body=body, timeout=30.0)
                                _show_api_response(r)
                            except requests.RequestException as ex:
                                st.error(f"Connection error: {ex}")

                adm_pl_pjson = st.text_area(
                    "admin PATCH …/pipeline JSON",
                    height=90,
                    key="api_adm_pl_pjson",
                    value=json.dumps({"interview_stage": "scheduled", "offer_outcome": ""}, indent=2),
                )
                if st.button("PATCH /api/admin/applications/{id}/pipeline", key="api_adm_pl_patch"):
                    if not (adm_patch_id or "").strip():
                        st.error("Enter application_id")
                    else:
                        try:
                            body = json.loads(adm_pl_pjson)
                        except json.JSONDecodeError as je:
                            st.error(f"Invalid JSON: {je}")
                        else:
                            try:
                                path = f"/api/admin/applications/{quote(adm_patch_id.strip(), safe='')}/pipeline"
                                r = _call("PATCH", path, json_body=body, timeout=30.0)
                                _show_api_response(r)
                            except requests.RequestException as ex:
                                st.error(f"Connection error: {ex}")

        st.caption(
            "Browser automation (confirm Easy Apply, apply-to-jobs) is not triggered here — "
            "see scripts/README.md (needs ATS_ALLOW_LINKEDIN_BROWSER on the API)."
        )
