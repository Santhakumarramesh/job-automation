"""
Career Co-Pilot Pro — Candidate App
Guided 7-stage workflow for job seekers.
Clean, simple, no internal tooling exposed.

Stages: Setup → Discover → Score → Prepare → Review → Apply → Track
"""

import json
import os
import pathlib
import re
import base64

import streamlit as st
import pandas as pd
from dotenv import load_dotenv

# ── path helpers ────────────────────────────────────────────────────────────
_SCRIPT_DIR = pathlib.Path(__file__).resolve().parent.parent
_PROFILE_PATH = _SCRIPT_DIR / "config" / "candidate_profile.json"
_MASTER_RESUMES_DIR = _SCRIPT_DIR / "Master_Resumes"

# ── service imports (lazy-safe) ─────────────────────────────────────────────
def _svc(name):
    """Lazy-import guard: surface ImportError as Streamlit error."""
    try:
        import importlib
        return importlib.import_module(name)
    except ImportError as e:
        st.error(f"Service unavailable: {name} — {e}")
        return None


# ────────────────────────────────────────────────────────────────────────────
# SETUP CHECKLIST
# ────────────────────────────────────────────────────────────────────────────

def _setup_status() -> dict:
    """Return dict of setup item → (bool ok, str detail)."""
    items = {}

    # 1. OpenAI key
    has_oai = bool((os.getenv("OPENAI_API_KEY") or "").strip())
    items["openai_key"] = (has_oai, "Set OPENAI_API_KEY" if not has_oai else "OpenAI API key present")

    # 2. Resume
    has_resume = bool(st.session_state.get("resume_bytes"))
    items["resume"] = (has_resume, "Upload your resume (PDF)" if not has_resume else "Resume loaded")

    # 3. Profile
    try:
        from services.profile_service import load_profile, validate_profile, AUTO_APPLY_REQUIRED
        prof = load_profile()
        missing = [k for k in AUTO_APPLY_REQUIRED if not str(prof.get(k) or "").strip()]
        if missing:
            items["profile"] = (False, f"Complete profile: {', '.join(missing[:3])}")
        else:
            warn = validate_profile(prof)
            items["profile"] = (len(warn) == 0, "Profile complete" if not warn else f"{len(warn)} profile warnings")
    except Exception:
        items["profile"] = (False, "Edit config/candidate_profile.json")

    return items


def _render_setup_banner():
    """Show green banner if ready; amber checklist if not."""
    status = _setup_status()
    all_ok = all(v[0] for v in status.values())
    if all_ok:
        st.success("✅ Setup complete — you are ready to apply.")
        return True

    st.warning("**Complete setup to unlock all stages.**")
    cols = st.columns(len(status))
    icons = {"openai_key": "🔑", "resume": "📄", "profile": "👤"}
    for i, (key, (ok, detail)) in enumerate(status.items()):
        icon = icons.get(key, "•")
        label = "✅" if ok else "⚪"
        cols[i].metric(f"{icon} {label}", detail[:40])
    return False


# ────────────────────────────────────────────────────────────────────────────
# SIDEBAR  (non-sensitive only in candidate mode)
# ────────────────────────────────────────────────────────────────────────────

def _render_sidebar() -> dict:
    """Render sidebar; return dict of session values."""
    st.sidebar.image("https://img.icons8.com/fluency/96/rocket.png", width=48)
    st.sidebar.title("Career Co-Pilot Pro")
    st.sidebar.markdown("---")

    # Resume selector
    st.sidebar.subheader("📄 Your Resume")
    master_pdfs = sorted(_MASTER_RESUMES_DIR.glob("*.pdf")) if _MASTER_RESUMES_DIR.exists() else []
    if master_pdfs:
        choices = ["— Upload new —"] + [p.name for p in master_pdfs]
        pick = st.sidebar.selectbox("Master resume", choices, key="sidebar_master_pick")
        if pick != "— Upload new —":
            sel_path = _MASTER_RESUMES_DIR / pick
            if sel_path.exists():
                st.session_state["resume_bytes"] = sel_path.read_bytes()
                st.session_state["resume_name"] = pick

    uploaded = st.sidebar.file_uploader("Or upload PDF", type=["pdf"], key="sidebar_upload")
    if uploaded:
        st.session_state["resume_bytes"] = uploaded.read()
        st.session_state["resume_name"] = uploaded.name

    if st.session_state.get("resume_bytes"):
        st.sidebar.success(f"✓ {st.session_state.get('resume_name', 'resume.pdf')}")

    st.sidebar.markdown("---")

    # Profile quick-view (read-only)
    try:
        from services.profile_service import load_profile, validate_profile
        prof = load_profile()
        name = prof.get("full_name") or prof.get("name") or ""
        email = prof.get("email") or ""
        if name:
            st.sidebar.caption(f"👤 {name}")
        if email:
            st.sidebar.caption(f"📧 {email}")
        warns = validate_profile(prof)
        if warns:
            with st.sidebar.expander(f"⚠️ {len(warns)} profile notes"):
                for w in warns[:5]:
                    st.caption(w)
        else:
            st.sidebar.caption("✅ Profile complete")
    except Exception:
        st.sidebar.caption("Edit config/candidate_profile.json")

    st.sidebar.markdown("---")
    st.sidebar.caption("Operator mode? Set APP_MODE=operator")

    return {}


# ────────────────────────────────────────────────────────────────────────────
# STAGE NAVIGATION
# ────────────────────────────────────────────────────────────────────────────

STAGES = [
    ("⚙️", "Setup"),
    ("🔍", "Discover"),
    ("📊", "Score"),
    ("✏️", "Prepare"),
    ("🛡️", "Review"),
    ("🚀", "Apply"),
    ("📋", "Track"),
]

def _stage_nav():
    """Render horizontal stage tabs; return selected stage index."""
    labels = [f"{icon} {name}" for icon, name in STAGES]
    stage = st.session_state.get("current_stage", 0)
    cols = st.columns(len(STAGES))
    for i, (label, col) in enumerate(zip(labels, cols)):
        active = (i == stage)
        style = "primary" if active else "secondary"
        if col.button(label, key=f"stage_btn_{i}", type=style, use_container_width=True):
            st.session_state["current_stage"] = i
            st.rerun()
    st.markdown("---")
    return st.session_state.get("current_stage", 0)


# ────────────────────────────────────────────────────────────────────────────
# STAGE 0: SETUP
# ────────────────────────────────────────────────────────────────────────────

def stage_setup():
    st.header("⚙️ Setup")
    st.markdown("Complete all three items below before moving to the next stage.")

    # ── OpenAI key ──────────────────────────────────────────────────────────
    st.subheader("1. API Key")
    allow_env_write = os.getenv("ALLOW_ENV_WRITE", "").lower() in ("1", "true", "yes")
    current_key = os.getenv("OPENAI_API_KEY", "")

    if current_key:
        st.success("✅ OpenAI API key is set via environment variable.")
    else:
        st.info("Set OPENAI_API_KEY in your environment, or enter it below for this session only.")
        session_key = st.text_input(
            "OpenAI API Key (session only — not saved to disk)",
            type="password",
            key="setup_oai_key",
        )
        if session_key:
            os.environ["OPENAI_API_KEY"] = session_key
            st.success("✅ Key loaded for this session.")

    # ── Resume ──────────────────────────────────────────────────────────────
    st.subheader("2. Base Resume")
    if st.session_state.get("resume_bytes"):
        st.success(f"✅ Resume loaded: {st.session_state.get('resume_name', 'resume.pdf')}")
    else:
        st.info("Upload your base resume (PDF) in the sidebar or select from Master Resumes.")

    # ── Profile ─────────────────────────────────────────────────────────────
    st.subheader("3. Candidate Profile")
    try:
        from services.profile_service import load_profile, validate_profile, AUTO_APPLY_REQUIRED, ensure_profile_exists
        ensure_profile_exists()
        prof = load_profile()
        missing = [k for k in AUTO_APPLY_REQUIRED if not str(prof.get(k) or "").strip()]
        warns = validate_profile(prof)

        col1, col2 = st.columns(2)
        col1.metric("Required fields", f"{len(AUTO_APPLY_REQUIRED) - len(missing)} / {len(AUTO_APPLY_REQUIRED)}")
        col2.metric("Profile warnings", str(len(warns)))

        if missing:
            st.warning(f"Missing required fields: **{', '.join(missing)}**")
            st.code("# Edit this file:\nconfig/candidate_profile.json", language="bash")
        elif warns:
            with st.expander("Profile warnings (optional)"):
                for w in warns:
                    st.caption(f"⚠️ {w}")
            st.info("Profile is usable. Warnings are optional improvements.")
        else:
            st.success("✅ Profile is complete and valid.")

        # profile preview
        with st.expander("View profile summary"):
            for key in ["full_name", "email", "phone", "location", "linkedin_url", "years_experience"]:
                val = prof.get(key)
                if val:
                    st.caption(f"**{key}:** {str(val)[:80]}")

    except Exception as e:
        st.error(f"Could not load profile: {e}")
        st.code("cp config/candidate_profile.example.json config/candidate_profile.json", language="bash")

    st.markdown("---")
    status = _setup_status()
    all_ok = all(v[0] for v in status.values())
    if all_ok:
        st.success("🎉 All setup items complete! Move to **Discover** to find your first job.")
        if st.button("Continue to Discover →", type="primary"):
            st.session_state["current_stage"] = 1
            st.rerun()
    else:
        pending = [detail for ok, detail in status.values() if not ok]
        st.warning("Still needed: " + " · ".join(pending))


# ────────────────────────────────────────────────────────────────────────────
# STAGE 1: DISCOVER
# ────────────────────────────────────────────────────────────────────────────

def stage_discover():
    st.header("🔍 Discover")
    st.markdown("Find jobs by pasting a URL, entering a job description, or using AI job search.")

    discover_mode = st.radio(
        "How do you want to find jobs?",
        ["Paste a job URL", "Paste a job description", "AI job search"],
        horizontal=True,
        key="discover_mode",
    )

    if discover_mode == "Paste a job URL":
        url = st.text_input("Job posting URL", placeholder="https://www.linkedin.com/jobs/view/...", key="discover_url")
        if st.button("Fetch job description", type="primary", key="discover_fetch"):
            if not url.strip():
                st.error("Enter a URL first.")
            else:
                with st.spinner("Fetching job description..."):
                    try:
                        import requests
                        from bs4 import BeautifulSoup
                        headers = {"User-Agent": "Mozilla/5.0"}
                        resp = requests.get(url.strip(), headers=headers, timeout=12)
                        soup = BeautifulSoup(resp.content, "html.parser")
                        for tag in soup(["script", "style", "nav", "footer"]):
                            tag.extract()
                        jd = soup.get_text(separator=" ", strip=True)
                        st.session_state["jd_text"] = jd[:12000]
                        st.session_state["jd_url"] = url.strip()
                        st.success(f"Fetched {len(jd):,} chars of job description.")
                    except Exception as e:
                        st.error(f"Could not fetch URL: {e}")

    elif discover_mode == "Paste a job description":
        jd_input = st.text_area("Paste the full job description here", height=300, key="discover_jd_paste")
        url_input = st.text_input("Job posting URL (optional)", key="discover_jd_url")
        if st.button("Use this job description", type="primary"):
            if jd_input.strip():
                st.session_state["jd_text"] = jd_input.strip()
                st.session_state["jd_url"] = url_input.strip()
                st.success("Job description saved.")
            else:
                st.error("Paste a job description first.")

    else:  # AI job search
        st.info("AI job search uses Apify or LinkedIn MCP to find matching roles based on your resume.")
        apify_key = os.getenv("APIFY_API_KEY") or os.getenv("APIFY_API_TOKEN") or ""
        if not apify_key:
            st.warning("Set APIFY_API_KEY to enable AI job search. You can also use LinkedIn MCP without it.")

        source = st.selectbox("Search source", ["LinkedIn MCP", "Apify", "Both"], key="discover_ai_source")
        max_jobs = st.slider("Max results", 5, 100, 20, key="discover_max_jobs")

        if st.button("Search for jobs", type="primary", key="discover_ai_search"):
            if not st.session_state.get("resume_bytes"):
                st.error("Upload your resume first (sidebar).")
            else:
                with st.spinner("Searching for matching jobs..."):
                    try:
                        from services.document_service import extract_text_from_pdf
                        from services.job_search_service import get_jobs
                        provider_map = {"LinkedIn MCP": "linkedin_mcp", "Apify": "apify", "Both": "both"}
                        resume_text = extract_text_from_pdf(st.session_state["resume_bytes"])
                        jobs_df = get_jobs(
                            resume_text=resume_text,
                            provider=provider_map[source],
                            apify_api_key=apify_key,
                            max_results=max_jobs,
                        )
                        if not jobs_df.empty:
                            st.session_state["jobs_df"] = jobs_df
                            st.success(f"Found {len(jobs_df)} matching jobs.")
                        else:
                            st.warning("No jobs found. Try a different source or check your LinkedIn/Apify credentials.")
                    except Exception as e:
                        st.error(f"Search failed: {e}")

        if "jobs_df" in st.session_state:
            df = st.session_state["jobs_df"]
            st.subheader(f"Found {len(df)} jobs")
            for col in ["title", "company", "location"]:
                if col not in df.columns:
                    df[col] = ""

            sel_col = "Select"
            if sel_col not in df.columns:
                df[sel_col] = False
            st.session_state["jobs_df"] = df

            edited = st.data_editor(
                df[["Select", "title", "company", "location"]].head(50),
                column_config={"Select": st.column_config.CheckboxColumn("Select")},
                hide_index=True,
                key="discover_job_editor",
            )
            if edited is not None:
                st.session_state["jobs_df"]["Select"] = edited["Select"]

            if st.button("Use selected job for next stages", type="primary", key="discover_pick_job"):
                sel = df[df.get("Select", False).fillna(False).astype(bool)]
                if sel.empty:
                    st.error("Select at least one job.")
                else:
                    row = sel.iloc[0]
                    st.session_state["jd_text"] = str(row.get("description", ""))[:12000]
                    st.session_state["jd_url"] = str(row.get("url") or row.get("applyUrl") or "")
                    st.session_state["jd_title"] = str(row.get("title", ""))
                    st.session_state["jd_company"] = str(row.get("company", ""))
                    st.success(f"Selected: {row.get('title', '')} at {row.get('company', '')}")

    # Show current job if loaded
    if st.session_state.get("jd_text"):
        st.markdown("---")
        st.success("**Job description loaded.** You can proceed to Score.")
        with st.expander("Preview job description"):
            st.write(st.session_state["jd_text"][:2000] + ("..." if len(st.session_state.get("jd_text", "")) > 2000 else ""))

        col1, col2, col3 = st.columns(3)
        col1.text_input("Company", value=st.session_state.get("jd_company", ""), key="jd_company_input",
                        on_change=lambda: st.session_state.update({"jd_company": st.session_state["jd_company_input"]}))
        col2.text_input("Role", value=st.session_state.get("jd_title", "AI/ML Engineer"), key="jd_title_input",
                        on_change=lambda: st.session_state.update({"jd_title": st.session_state["jd_title_input"]}))
        col3.text_input("Location", value=st.session_state.get("jd_location", ""), key="jd_location_input",
                        on_change=lambda: st.session_state.update({"jd_location": st.session_state["jd_location_input"]}))

        if st.button("Continue to Score →", type="primary"):
            st.session_state["current_stage"] = 2
            st.rerun()


# ────────────────────────────────────────────────────────────────────────────
# STAGE 2: SCORE
# ────────────────────────────────────────────────────────────────────────────

def stage_score():
    st.header("📊 Score")
    st.markdown("See how well your resume matches this job before investing time tailoring it.")

    if not st.session_state.get("resume_bytes"):
        st.warning("Upload your resume in the sidebar first.")
        return
    if not st.session_state.get("jd_text"):
        st.warning("Go to **Discover** first and load a job description.")
        return

    company = st.session_state.get("jd_company", "")
    title = st.session_state.get("jd_title", "AI/ML Engineer")
    location = st.session_state.get("jd_location", "")
    jd = st.session_state.get("jd_text", "")

    try:
        from services.profile_service import load_profile
        prof = load_profile()
        name = prof.get("full_name") or "Candidate"
    except Exception:
        prof = {}
        name = "Candidate"

    col1, col2 = st.columns(2)
    col1.info(f"**Job:** {title} at {company or '(company)'}")
    col2.info(f"**Resume:** {st.session_state.get('resume_name', 'uploaded resume')}")

    if st.button("Run fit & ATS score", type="primary", key="score_run"):
        if not os.getenv("OPENAI_API_KEY"):
            st.error("Set OPENAI_API_KEY first (Setup stage).")
            return
        with st.spinner("Scoring your resume against this job..."):
            try:
                from services.document_service import extract_text_from_pdf
                from services.ats_service import score_resume, check_fit_gate
                from agents.state import AgentState

                resume_text = extract_text_from_pdf(st.session_state["resume_bytes"])
                state: AgentState = {
                    "candidate_name": name,
                    "target_position": title,
                    "target_company": company,
                    "target_location": location,
                    "base_resume_text": resume_text,
                    "job_description": jd,
                }
                fit_result = check_fit_gate(state)
                state.update(fit_result)
                score_result = score_resume(state, target_score=100)
                state.update(score_result)
                st.session_state["score_state"] = state
            except Exception as e:
                st.error(f"Scoring failed: {e}")
                return

    if st.session_state.get("score_state"):
        s = st.session_state["score_state"]

        # ── Trust card ──────────────────────────────────────────────────────
        st.markdown("### Application Readiness")
        ats = s.get("initial_ats_score") or s.get("final_ats_score") or 0
        fit = s.get("job_fit_score") or 0
        ceiling = s.get("truth_safe_ats_ceiling")
        fit_decision = str(s.get("fit_decision") or "").lower()
        missing_skills = s.get("missing_skills") or []
        unsupported = s.get("unsupported_requirements") or []
        ceiling_reason = s.get("truth_safe_ceiling_reason") or ""
        is_eligible = s.get("is_eligible", True)
        elig_reason = s.get("eligibility_reason", "")

        col1, col2, col3 = st.columns(3)
        col1.metric("ATS Match Score", f"{ats}%", help="How well your resume keywords match the job description.")
        if ceiling is not None:
            col2.metric("Truth-safe ceiling", f"{ceiling}%", help="Maximum honest ATS score based only on your actual skills.")
        col3.metric("Fit decision", fit_decision.upper() if fit_decision else "—")

        if not is_eligible:
            st.error(f"**Not eligible:** {elig_reason}")
        elif fit_decision == "apply":
            st.success("**Ready to apply.** Your profile is a strong match for this role.")
        elif fit_decision == "manual_review":
            st.warning("**Review recommended.** Some gaps exist — see details below.")
        elif fit_decision == "reject":
            st.error("**Not recommended.** Significant gaps between your profile and this role.")

        if missing_skills:
            with st.expander(f"Skill gaps ({len(missing_skills)} missing)"):
                st.write(", ".join(missing_skills))
        if unsupported:
            with st.expander(f"Requirements we cannot claim ({len(unsupported)})"):
                st.info("These items were NOT added to your resume — we only include what you can truthfully claim.")
                st.write(", ".join(str(x) for x in unsupported))
        if ceiling_reason:
            with st.expander("Why is the truth-safe ceiling set here?"):
                st.write(ceiling_reason)

        st.markdown("---")
        go_col1, go_col2 = st.columns(2)
        if go_col1.button("Continue to Prepare →", type="primary"):
            st.session_state["current_stage"] = 3
            st.rerun()
        if go_col2.button("↩ Change job (Discover)"):
            st.session_state["current_stage"] = 1
            st.rerun()


# ────────────────────────────────────────────────────────────────────────────
# STAGE 3: PREPARE
# ────────────────────────────────────────────────────────────────────────────

def stage_prepare():
    st.header("✏️ Prepare")
    st.markdown("Generate a tailored resume and cover letter for this specific job.")

    if not st.session_state.get("resume_bytes"):
        st.warning("Upload your resume first.")
        return
    if not st.session_state.get("jd_text"):
        st.warning("Load a job description in Discover first.")
        return

    score_state = st.session_state.get("score_state", {})
    fit_decision = str(score_state.get("fit_decision") or "").lower()
    if fit_decision == "reject":
        st.error("The fit score for this job is too low to proceed. Go back to Discover and choose a better-matched role.")
        return

    company = st.session_state.get("jd_company", "Company")
    title = st.session_state.get("jd_title", "AI/ML Engineer")
    location = st.session_state.get("jd_location", "")

    try:
        from services.profile_service import load_profile
        prof = load_profile()
        name = prof.get("full_name") or "Candidate"
    except Exception:
        prof = {}
        name = "Candidate"

    use_iterative = st.checkbox(
        "Use iterative ATS optimizer (slower, higher score)",
        value=True,
        help="Runs multiple rounds of tailoring targeting the highest truth-safe ATS score.",
    )

    if st.button("Generate tailored documents", type="primary", key="prepare_run"):
        if not os.getenv("OPENAI_API_KEY"):
            st.error("Set OPENAI_API_KEY first.")
            return
        with st.spinner("Generating tailored resume and cover letter... (this takes 1–2 minutes)"):
            try:
                from services.document_service import (
                    extract_text_from_pdf, tailor, humanize_resume_text,
                    generate_cover_letter_from_state, humanize_cover_letter_text,
                    save_documents_to_pdf,
                )
                from services.ats_service import run_iterative_ats, score_resume
                from agents.intelligent_project_generator import intelligent_project_generator
                from agents.state import AgentState

                resume_text = extract_text_from_pdf(st.session_state["resume_bytes"])
                state: AgentState = dict(score_state) if score_state else {}
                state.update({
                    "candidate_name": name,
                    "target_position": title,
                    "target_company": company,
                    "target_location": location,
                    "base_resume_text": resume_text,
                    "job_description": st.session_state["jd_text"],
                    "user_id": "streamlit-candidate",
                })

                if use_iterative:
                    state.update(run_iterative_ats(state, target_score=100, max_attempts=5, truth_safe=True))
                else:
                    state.update(score_resume(state, target_score=100))
                    state.update(tailor(state))
                    state.update(humanize_resume_text(state))

                state.update(intelligent_project_generator(state))
                state.update(generate_cover_letter_from_state(state))
                state.update(humanize_cover_letter_text(state))
                state.update(save_documents_to_pdf(state))

                st.session_state["prepare_state"] = state
                st.success("Documents ready!")
            except Exception as e:
                st.error(f"Preparation failed: {e}")

    if st.session_state.get("prepare_state"):
        s = st.session_state["prepare_state"]
        final_ats = s.get("final_ats_score") or s.get("initial_ats_score") or 0
        ceiling = s.get("truth_safe_ats_ceiling")

        col1, col2 = st.columns(2)
        col1.metric("Final ATS score", f"{final_ats}%")
        if ceiling:
            col2.metric("Truth-safe ceiling", f"{ceiling}%")

        import os as _os
        dl_col1, dl_col2, dl_col3 = st.columns(3)
        if s.get("final_pdf_path") and _os.path.isfile(s["final_pdf_path"]):
            with open(s["final_pdf_path"], "rb") as f:
                dl_col1.download_button("📄 Tailored Resume (PDF)", f.read(),
                    _os.path.basename(s["final_pdf_path"]), "application/pdf", use_container_width=True)
        if s.get("cover_letter_pdf_path") and _os.path.isfile(s["cover_letter_pdf_path"]):
            with open(s["cover_letter_pdf_path"], "rb") as f:
                dl_col2.download_button("✉️ Cover Letter (PDF)", f.read(),
                    _os.path.basename(s["cover_letter_pdf_path"]), "application/pdf", use_container_width=True)
        if s.get("ats_report_path") and _os.path.isfile(s["ats_report_path"]):
            with open(s["ats_report_path"], "rb") as f:
                dl_col3.download_button("📊 ATS Report (Excel)", f.read(),
                    _os.path.basename(s["ats_report_path"]),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True)

        if s.get("generated_project_text"):
            with st.expander("💡 Suggested project to bridge skill gaps"):
                st.markdown(s["generated_project_text"])

        if st.button("Continue to Review →", type="primary"):
            st.session_state["current_stage"] = 4
            st.rerun()


# ────────────────────────────────────────────────────────────────────────────
# STAGE 4: REVIEW
# ────────────────────────────────────────────────────────────────────────────

def _render_trust_card(decision: dict):
    """Render a plain-language trust card from a build_application_decision result."""
    job_state = str(decision.get("job_state") or "")
    safe_to_submit = bool(decision.get("safe_to_submit", False))
    policy_reason = str(decision.get("policy_reason") or "")
    answers = decision.get("answers") or {}
    critical = decision.get("critical_unsatisfied") or []
    fit_dec = str(decision.get("fit_decision") or "")

    # Header status
    if safe_to_submit and job_state == "safe_auto_apply":
        st.success("✅ **Ready for assisted submission** — all screening fields are truth-safe.")
    elif job_state == "manual_assist":
        st.info("📋 **Manual assist mode** — documents are prepared. You will submit this one yourself.")
    elif job_state == "manual_review":
        st.warning("🔍 **Review required** — some fields need your attention before applying.")
    elif job_state in ("skip", "blocked"):
        st.error(f"🚫 **Not applying** — {policy_reason or job_state}")
    else:
        st.info(f"Status: {job_state or 'pending'}")

    # Metrics row
    ans_states = [str((v or {}).get("answer_state") or "") for v in answers.values()] if isinstance(answers, dict) else []
    n_safe = ans_states.count("safe")
    n_review = ans_states.count("review")
    n_missing = ans_states.count("missing")
    n_blocked = ans_states.count("blocked")
    total = len(ans_states)

    if total:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Safe fields", f"{n_safe} / {total}", help="Fields we can answer truthfully")
        c2.metric("Needs review", str(n_review), help="Fields flagged for your verification")
        c3.metric("Missing", str(n_missing), help="Fields we could not answer — check your profile")
        c4.metric("Blocked", str(n_blocked), help="Fields that prevent auto-submit")

    if critical:
        st.warning("**Must resolve before auto-apply:** " + ", ".join(str(x) for x in critical))

    # Per-field table (review + missing only by default)
    if isinstance(answers, dict) and answers:
        from agents.application_answerer import CANONICAL_SCREENING_FIELD_LABELS
        order = {"missing": 0, "blocked": 1, "review": 2, "safe": 3}
        rows = []
        for k, meta in answers.items():
            if not isinstance(meta, dict):
                continue
            ast = str(meta.get("answer_state") or "")
            rows.append({
                "Question": CANONICAL_SCREENING_FIELD_LABELS.get(k, k),
                "Status": ast.upper(),
                "Our answer": str(meta.get("text") or "")[:120],
                "Truth-safe": "✅" if meta.get("truth_safe") else "⚠️",
            })
        rows.sort(key=lambda r: order.get(r["Status"].lower(), 9))

        show_all = st.checkbox("Show all fields (including safe)", value=False, key="review_show_all")
        display = rows if show_all else [r for r in rows if r["Status"] in ("MISSING", "REVIEW", "BLOCKED")]
        if display:
            st.dataframe(pd.DataFrame(display), hide_index=True, use_container_width=True)
        elif not show_all:
            st.success("All screening fields are safe — nothing to review.")


def stage_review():
    st.header("🛡️ Review")
    st.markdown("See exactly what will be submitted on your behalf, and confirm it is accurate.")

    if not st.session_state.get("jd_text"):
        st.warning("Load a job in Discover first.")
        return

    jd = st.session_state.get("jd_text", "")
    company = st.session_state.get("jd_company", "")
    title = st.session_state.get("jd_title", "AI/ML Engineer")
    prepare_state = st.session_state.get("prepare_state", {})
    jd_url = st.session_state.get("jd_url", "")

    if st.button("Run application decision check", type="primary", key="review_run"):
        with st.spinner("Checking all screening fields and safety gates..."):
            try:
                from services.document_service import extract_text_from_pdf
                from services.application_decision import build_application_decision
                from services.profile_service import load_profile
                import re as _re

                prof = load_profile()
                master_text = ""
                if st.session_state.get("resume_bytes"):
                    master_text = extract_text_from_pdf(st.session_state["resume_bytes"])

                job_dict = {
                    "url": jd_url,
                    "apply_url": jd_url,
                    "title": title,
                    "company": company,
                    "description": jd,
                    "easy_apply_confirmed": "linkedin.com" in jd_url.lower(),
                    "unsupported_requirements": prepare_state.get("unsupported_requirements") or [],
                    "fit_decision": prepare_state.get("fit_decision") or "",
                    "ats_score": prepare_state.get("final_ats_score") or prepare_state.get("initial_ats_score"),
                }
                decision = build_application_decision(
                    job_dict,
                    profile=prof,
                    master_resume_text=master_text,
                    use_llm_preview=False,
                )
                st.session_state["review_decision"] = decision
            except Exception as e:
                st.error(f"Decision check failed: {e}")

    if st.session_state.get("review_decision"):
        _render_trust_card(st.session_state["review_decision"])
        st.markdown("---")
        col1, col2 = st.columns(2)
        if col1.button("Continue to Apply →", type="primary"):
            st.session_state["current_stage"] = 5
            st.rerun()
        if col2.button("↩ Regenerate documents (Prepare)"):
            st.session_state["current_stage"] = 3
            st.rerun()

    else:
        st.info("Click the button above to check your application readiness.")


# ────────────────────────────────────────────────────────────────────────────
# STAGE 5: APPLY
# ────────────────────────────────────────────────────────────────────────────

def stage_apply():
    st.header("🚀 Apply")
    st.markdown("Submit your application or hand off to manual apply with all documents ready.")

    decision = st.session_state.get("review_decision")
    prepare_state = st.session_state.get("prepare_state", {})
    jd_url = st.session_state.get("jd_url", "")
    title = st.session_state.get("jd_title", "")
    company = st.session_state.get("jd_company", "")

    job_state = str((decision or {}).get("job_state") or "")
    safe_to_submit = bool((decision or {}).get("safe_to_submit", False))

    if not decision:
        st.warning("Complete the **Review** stage first.")
        return

    # ── LinkedIn Easy Apply path ─────────────────────────────────────────
    is_linkedin = "linkedin.com" in jd_url.lower()
    if is_linkedin and safe_to_submit and job_state == "safe_auto_apply":
        st.success("✅ This job is eligible for **LinkedIn Easy Apply** via the Career Co-Pilot assistant.")
        st.markdown("""
**What happens next:**
1. The assistant fills in all screening questions using your profile
2. You see a preview before anything is submitted
3. You approve the final submission — nothing is sent without your confirmation
        """)
        col1, col2 = st.columns(2)
        dry_run = col2.checkbox("Dry run (fill but do not submit)", value=False)
        if col1.button("Start LinkedIn Easy Apply", type="primary"):
            st.info("To use LinkedIn Easy Apply via the MCP assistant, open the Career Co-Pilot MCP in Claude Desktop and run: **apply_to_jobs**")
            if jd_url:
                st.code(f'''# Run in Claude Desktop (Career Co-Pilot MCP)
apply_to_jobs with jobs: [
  {{
    "url": "{jd_url}",
    "title": "{title}",
    "company": "{company}",
    "easy_apply_confirmed": true,
    "pilot_submit_allowed": true
  }}
]
dry_run: {str(dry_run).lower()}
''', language="json")

    # ── Manual assist path ────────────────────────────────────────────────
    elif job_state == "manual_assist" or not is_linkedin:
        st.info("📋 **Manual assist mode** — your documents are ready. Apply directly on the employer portal.")
        st.markdown("""
**Your documents are prepared and waiting:**
- Tailored resume (downloaded in Prepare stage)
- Cover letter (downloaded in Prepare stage)
- Screening answers pre-filled below — copy these into the application form
        """)
        if jd_url:
            st.link_button("Open job posting →", jd_url, use_container_width=True)

        # Show screening answers for copy-paste
        answers = decision.get("answers") or {}
        if answers:
            st.subheader("Screening answers (copy into the form)")
            from agents.application_answerer import CANONICAL_SCREENING_FIELD_LABELS
            answer_lines = []
            for k, meta in answers.items():
                if not isinstance(meta, dict):
                    continue
                text = str(meta.get("text") or "").strip()
                label = CANONICAL_SCREENING_FIELD_LABELS.get(k, k)
                if text:
                    answer_lines.append(f"{label}: {text}")
            if answer_lines:
                st.text_area("Copy answers", "\n\n".join(answer_lines), height=250)

    # ── Blocked / skip ────────────────────────────────────────────────────
    elif job_state in ("skip", "blocked"):
        st.error(f"**Not applying to this job.** Reason: {decision.get('policy_reason') or job_state}")
        st.info("Go back to Discover and find a better-matched role.")
        if st.button("↩ Go to Discover"):
            st.session_state["current_stage"] = 1
            st.rerun()
    else:
        st.warning(f"Application status: **{job_state}**. Review the decision details.")

    # ── Log to tracker ────────────────────────────────────────────────────
    st.markdown("---")
    if st.button("✅ Mark as applied & go to Track", key="apply_log"):
        try:
            from services.application_service import log_to_tracker
            from agents.state import AgentState
            state: AgentState = dict(prepare_state)
            state.update({
                "target_company": company,
                "target_position": title,
                "user_id": "streamlit-candidate",
                "job_state": job_state,
                "submission_status": "applied",
            })
            log_to_tracker(state)
            st.success("Logged to tracker.")
        except Exception as e:
            st.warning(f"Could not log to tracker: {e}")
        st.session_state["current_stage"] = 6
        st.rerun()


# ────────────────────────────────────────────────────────────────────────────
# STAGE 6: TRACK
# ────────────────────────────────────────────────────────────────────────────

def stage_track():
    st.header("📋 Track")
    st.markdown("Your application history, follow-up queue, and insights.")

    tabs = st.tabs(["Applications", "Follow-ups", "Insights"])

    with tabs[0]:
        try:
            from services.application_service import get_applications
            df = get_applications(user_id="streamlit-candidate", limit=100)
            if df is None or (hasattr(df, 'empty') and df.empty):
                st.info("No applications tracked yet. Apply to some jobs and they will appear here.")
            else:
                st.metric("Total applications", len(df))
                display_cols = [c for c in ["company", "position", "job_state", "status", "created_at"] if c in df.columns]
                st.dataframe(df[display_cols] if display_cols else df, hide_index=True, use_container_width=True)
        except Exception as e:
            st.error(f"Could not load applications: {e}")

    with tabs[1]:
        try:
            from services.follow_up_service import list_follow_ups as list_follow_up_queue
            follow_ups = list_follow_up_queue(user_id="streamlit-candidate", limit=50)
            if not follow_ups:
                st.info("No follow-ups queued.")
            else:
                st.metric("Follow-ups pending", len(follow_ups))
                st.dataframe(pd.DataFrame(follow_ups), hide_index=True, use_container_width=True)
        except Exception as e:
            st.error(f"Could not load follow-ups: {e}")

    with tabs[2]:
        try:
            from services.application_insights import build_application_insights
            insights = build_application_insights(user_id="streamlit-candidate")
            if insights:
                c1, c2, c3 = st.columns(3)
                c1.metric("Total applied", insights.get("total_applied", 0))
                c2.metric("Auto-apply", insights.get("auto_apply_count", 0))
                c3.metric("Manual assist", insights.get("manual_assist_count", 0))
                if insights.get("top_companies"):
                    st.subheader("Top companies applied to")
                    st.write(", ".join(insights["top_companies"][:10]))
            else:
                st.info("Not enough data for insights yet.")
        except Exception as e:
            st.error(f"Could not load insights: {e}")

    st.markdown("---")
    if st.button("Start a new application →", type="primary"):
        for key in ["jd_text", "jd_url", "jd_company", "jd_title", "jd_location",
                    "score_state", "prepare_state", "review_decision"]:
            st.session_state.pop(key, None)
        st.session_state["current_stage"] = 1
        st.rerun()


# ────────────────────────────────────────────────────────────────────────────
# MAIN
# ────────────────────────────────────────────────────────────────────────────

STAGE_HANDLERS = [
    stage_setup,
    stage_discover,
    stage_score,
    stage_prepare,
    stage_review,
    stage_apply,
    stage_track,
]


def run():
    load_dotenv()
    st.set_page_config(
        page_title="Career Co-Pilot Pro",
        page_icon="🚀",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    _render_sidebar()

    # Hero
    st.markdown(
        "<h1 style='margin-bottom:0'>🚀 Career Co-Pilot Pro</h1>"
        "<p style='color:#888;margin-top:4px'>Supervised application workflow · Truth-safe · Human in the loop</p>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    # Setup banner (shown on all stages except setup itself)
    stage = st.session_state.get("current_stage", 0)
    if stage > 0:
        _render_setup_banner()

    # Stage nav
    current = _stage_nav()

    # Dispatch
    STAGE_HANDLERS[current]()


if __name__ == "__main__":
    run()
