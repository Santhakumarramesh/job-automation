"""
Phase 11 — Career Co-Pilot: Production-Ready Candidate App
5-page supervised workflow:
  Page 1: Discover      — job search + prefilter
  Page 2: Review Queue  — score breakdown, grouped by readiness
  Page 3: Resume Review — tailored resume + approval per job
  Page 4: Apply Queue   — run approved jobs one by one
  Page 5: Tracker       — full lifecycle view
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run():
    st.set_page_config(
        page_title="Career Co-Pilot",
        page_icon="🧭",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # ── Sidebar nav ──────────────────────────────────────────────────────────
    with st.sidebar:
        st.title("🧭 Career Co-Pilot")
        st.caption("Supervised · Truthful · Production-Ready")
        st.divider()
        page = st.radio(
            "Navigate",
            ["1 · Discover", "2 · Review Queue", "3 · Resume Review", "4 · Apply Queue", "5 · Tracker"],
            label_visibility="collapsed",
        )
        st.divider()
        _render_sidebar_status()

    # ── Route ────────────────────────────────────────────────────────────────
    if page.startswith("1"):
        _page_discover()
    elif page.startswith("2"):
        _page_review_queue()
    elif page.startswith("3"):
        _page_resume_review()
    elif page.startswith("4"):
        _page_apply_queue()
    else:
        _page_tracker()


# ─────────────────────────────────────────────────────────────────────────────
# Page 1 — Discover
# ─────────────────────────────────────────────────────────────────────────────

def _page_discover():
    st.title("1 · Discover Jobs")
    st.caption("Search, prefilter, and score — only strong matches reach your queue.")

    with st.form("discover_form"):
        col1, col2 = st.columns(2)
        keywords = col1.text_input("Job Keywords", value="AI ML Engineer")
        location = col2.text_input("Location", value="Remote")
        col3, col4 = st.columns(2)
        limit = col3.slider("Max jobs to fetch", 5, 50, 20)
        easy_apply_only = col4.checkbox("Easy Apply only", value=True)
        submitted = st.form_submit_button("🔍 Search & Score", type="primary")

    if submitted:
        with st.spinner("Searching jobs and scoring against your resume…"):
            try:
                from services.resume_package_service import _load_master_resume_text
                from services.profile_service import load_profile
                from services.fit_engine import score_structured_fit, fit_result_to_dict
                from services.job_prefilter import prefilter_batch
                from services.apply_queue_service import upsert_queue_item

                resume_text = _load_master_resume_text()
                profile = load_profile() or {}

                # Try LinkedIn MCP search first
                jobs = _search_jobs(keywords, location, limit, easy_apply_only)

                if not jobs:
                    st.warning("No jobs returned from search. Try different keywords or paste jobs manually below.")
                    return

                st.info(f"Found {len(jobs)} jobs. Scoring and filtering…")

                result = prefilter_batch(jobs, resume_text=resume_text, profile=profile)

                # Add to queue
                for category in ["high_confidence", "review_fit"]:
                    for jr in result[category]:
                        url = jr.get("job_url", "")
                        if url:
                            upsert_queue_item(
                                job_url=url,
                                job_title=jr.get("job_title", ""),
                                company=jr.get("company", ""),
                                job_description=next(
                                    (j.get("description", "") for j in jobs
                                     if j.get("url") == url), ""
                                ),
                                fit_data=jr.get("fit", {}),
                            )

                st.success(f"✅ Scored {len(jobs)} jobs → {result['high_confidence_count']} high-confidence, "
                           f"{result['review_fit_count']} need review, {result['skip_count']} skipped")

                _render_prefilter_results(result)

                st.info("👉 Head to **2 · Review Queue** to approve jobs for applying.")

            except Exception as e:
                st.error(f"Discovery error: {e}")

    # Manual job paste
    with st.expander("📋 Or paste a job description manually"):
        with st.form("manual_job_form"):
            job_url = st.text_input("Job URL")
            job_title = st.text_input("Job Title")
            company = st.text_input("Company")
            job_desc = st.text_area("Job Description", height=200)
            add_btn = st.form_submit_button("Add to Queue")

        if add_btn and job_url and job_title:
            try:
                from services.resume_package_service import _load_master_resume_text
                from services.profile_service import load_profile
                from services.fit_engine import score_structured_fit, fit_result_to_dict
                from services.apply_queue_service import upsert_queue_item
                from enhanced_ats_checker import EnhancedATSChecker

                resume_text = _load_master_resume_text()
                profile = load_profile() or {}
                fit = score_structured_fit(job_title, job_desc, resume_text, profile)
                fit_dict = fit_result_to_dict(fit)

                ats_checker = EnhancedATSChecker()
                try:
                    ats_result = ats_checker.comprehensive_ats_check(
                        resume_text=resume_text,
                        job_description=job_desc,
                        job_title=job_title,
                        company_name=company,
                    )
                    ats_score = ats_result.get("ats_score", 0)
                except Exception:
                    ats_score = 0

                item_id = upsert_queue_item(
                    job_url=job_url, job_title=job_title, company=company,
                    job_description=job_desc, fit_data=fit_dict, ats_score=ats_score,
                )
                st.success(f"Added to queue (fit: {fit.overall_fit_score}/100, ATS: {ats_score}/100)")
            except Exception as e:
                st.error(f"Error: {e}")


def _search_jobs(keywords: str, location: str, limit: int, easy_apply_only: bool) -> list[dict]:
    """Try MCP search_jobs, return normalized list."""
    try:
        from services.job_search_service import search_jobs_payload
        result = search_jobs_payload(
            keywords=keywords, location=location,
            max_results=limit,
            easy_apply=easy_apply_only,
        )
        jobs = result.get("jobs", [])
        # Normalize field names
        normalized = []
        for j in jobs:
            normalized.append({
                "url": j.get("url", j.get("apply_url", j.get("job_url", ""))),
                "title": j.get("title", j.get("job_title", "")),
                "company": j.get("company", ""),
                "description": j.get("description", j.get("job_description", "")),
                "location": j.get("location", ""),
                "work_type": j.get("work_type", "remote"),
            })
        return normalized
    except Exception:
        return []


def _render_prefilter_results(result: dict):
    tab1, tab2, tab3 = st.tabs([
        f"✅ High Confidence ({result['high_confidence_count']})",
        f"🔍 Review Fit ({result['review_fit_count']})",
        f"⏭ Skipped ({result['skip_count']})",
    ])

    with tab1:
        for jr in result["high_confidence"]:
            _render_job_card(jr, badge_color="green")

    with tab2:
        for jr in result["review_fit"]:
            _render_job_card(jr, badge_color="orange")

    with tab3:
        for jr in result["skip"][:10]:
            st.caption(f"⏭ {jr.get('company')} — {jr.get('job_url', '')} — {jr.get('reason', '')}")


def _render_job_card(jr: dict, badge_color: str = "blue"):
    fit = jr.get("fit", {})
    with st.container(border=True):
        col1, col2 = st.columns([3, 1])
        col1.markdown(f"**{jr.get('job_title')}** @ {jr.get('company')}")
        col1.caption(jr.get("job_url", ""))
        with col2:
            st.metric("Fit", f"{fit.get('overall_fit_score', 0)}/100")
        
        c1, c2, c3 = st.columns(3)
        c1.caption(f"🎯 Role: {fit.get('role_family', 'unknown').replace('_', ' ')}")
        c2.caption(f"📊 Seniority: {fit.get('seniority_band', 'mid')}")
        c3.caption(f"🔬 Experience: {fit.get('experience_match_score', 0)}/100")

        if fit.get("hard_blockers"):
            st.warning(f"⚠️ Blockers: {'; '.join(fit['hard_blockers'])}")
        if fit.get("unsupported_requirements"):
            st.caption(f"Unsupported: {', '.join(fit['unsupported_requirements'][:3])}")


# ─────────────────────────────────────────────────────────────────────────────
# Page 2 — Review Queue
# ─────────────────────────────────────────────────────────────────────────────

def _page_review_queue():
    st.title("2 · Review Queue")
    st.caption("Jobs scored and ready for your decision. Approve the ones you want applied.")

    try:
        from services.apply_queue_service import (
            get_queue, get_queue_summary, approve_job, skip_job, hold_job,
            JobQueueState
        )

        summary = get_queue_summary()
        _render_queue_summary_badges(summary)

        tab_ready, tab_review, tab_approved, tab_skip = st.tabs([
            f"🟢 Ready ({summary.get('ready_for_approval', 0)})",
            f"🟡 Review Fit ({summary.get('review_fit', 0)})",
            f"✅ Approved ({summary.get('approved_for_apply', 0)})",
            f"⏭ Skipped ({summary.get('skip', 0)})",
        ])

        with tab_ready:
            items = get_queue(states=[JobQueueState.READY_FOR_APPROVAL])
            if not items:
                st.info("No jobs in 'ready for approval' state yet. Run Discovery first.")
            for item in items:
                _render_queue_item_card(item, show_approve=True)

        with tab_review:
            items = get_queue(states=[JobQueueState.REVIEW_FIT, JobQueueState.REVIEW_RESUME])
            for item in items:
                _render_queue_item_card(item, show_approve=True)

        with tab_approved:
            items = get_queue(states=[JobQueueState.APPROVED_FOR_APPLY])
            if not items:
                st.info("No approved jobs yet. Approve from Ready tab.")
            else:
                st.success(f"**{len(items)} job(s) approved** — go to Apply Queue to run them.")
            for item in items:
                _render_queue_item_card(item, show_approve=False)

        with tab_skip:
            items = get_queue(states=[JobQueueState.SKIP])
            for item in items[:20]:
                st.caption(f"⏭ {item.get('company')} · {item.get('job_title')} — {item.get('notes', item.get('fit_decision', ''))}")

    except Exception as e:
        st.error(f"Queue error: {e}")
        import traceback; st.code(traceback.format_exc())


def _render_queue_summary_badges(summary: dict):
    cols = st.columns(6)
    states = [
        ("ready_for_approval", "🟢 Ready", "green"),
        ("review_fit", "🟡 Review", "orange"),
        ("approved_for_apply", "✅ Approved", "green"),
        ("applying", "🔄 Applying", "blue"),
        ("applied", "📬 Applied", "gray"),
        ("blocked", "🚫 Blocked", "red"),
    ]
    for i, (state, label, _) in enumerate(states):
        cols[i].metric(label, summary.get(state, 0))


def _render_queue_item_card(item: dict, show_approve: bool = True):
    item_id = item["id"]
    with st.container(border=True):
        col1, col2, col3 = st.columns([4, 1, 2])
        col1.markdown(f"**{item.get('job_title')}** @ {item.get('company')}")
        col1.caption(item.get("job_url", ""))
        col2.metric("Fit", f"{item.get('overall_fit_score', 0)}/100")
        col2.metric("ATS", f"{item.get('ats_score', 0)}/100")

        if show_approve:
            with col3:
                a_col, h_col, s_col = st.columns(3)
                if a_col.button("✅ Approve", key=f"approve_{item_id}", type="primary"):
                    from services.apply_queue_service import approve_job
                    approve_job(item_id)
                    st.success("Approved!")
                    time.sleep(0.5)
                    st.rerun()
                if h_col.button("⏸ Hold", key=f"hold_{item_id}"):
                    from services.apply_queue_service import hold_job
                    hold_job(item_id)
                    st.rerun()
                if s_col.button("⏭ Skip", key=f"skip_{item_id}"):
                    from services.apply_queue_service import skip_job
                    skip_job(item_id)
                    st.rerun()

        # Detail expander
        with st.expander("View fit breakdown"):
            fit_reasons = item.get("fit_reasons", [])
            for r in (fit_reasons if isinstance(fit_reasons, list) else []):
                st.caption(f"• {r}")
            unsupported = item.get("unsupported_requirements", [])
            if unsupported:
                st.warning(f"Unsupported requirements: {', '.join(unsupported[:5])}")
            blockers = item.get("hard_blockers", [])
            if blockers:
                st.error(f"Hard blockers: {', '.join(blockers)}")


# ─────────────────────────────────────────────────────────────────────────────
# Page 3 — Resume Review
# ─────────────────────────────────────────────────────────────────────────────

def _page_resume_review():
    st.title("3 · Resume Review")
    st.caption("Generate a tailored resume for each approved job. Review before applying.")

    try:
        from services.apply_queue_service import (
            get_queue, attach_package, JobQueueState
        )
        from services.resume_package_service import generate_package_for_job, load_package

        items = get_queue(states=[JobQueueState.READY_FOR_APPROVAL, JobQueueState.APPROVED_FOR_APPLY])
        if not items:
            st.info("No jobs ready for resume generation. Approve jobs in Review Queue first.")
            return

        for item in items:
            item_id = item["id"]
            has_package = bool(item.get("resume_version_id"))

            with st.container(border=True):
                col1, col2 = st.columns([4, 2])
                col1.markdown(f"**{item.get('job_title')}** @ {item.get('company')}")
                col2.caption(f"Package: {item.get('package_status', 'not_generated')}")

                if not has_package:
                    if col2.button("🔧 Generate Tailored Resume", key=f"gen_{item_id}", type="primary"):
                        with st.spinner(f"Optimizing resume for {item.get('company')}…"):
                            pkg = generate_package_for_job(
                                job_title=item.get("job_title", ""),
                                company=item.get("company", ""),
                                job_description=item.get("job_description", ""),
                            )
                            attach_package(item_id, pkg)
                            st.success(f"Generated! ATS: {pkg.get('initial_ats_score')} → {pkg.get('final_ats_score')} "
                                       f"(ceiling: {pkg.get('truth_safe_ats_ceiling')})")
                            st.rerun()
                else:
                    pkg = load_package(item["resume_version_id"]) or {}
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Initial ATS", f"{pkg.get('initial_ats_score', 0)}/100")
                    c2.metric("Final ATS", f"{pkg.get('final_ats_score', 0)}/100")
                    c3.metric("Ceiling", f"{pkg.get('truth_safe_ats_ceiling', 0)}/100")

                    st.caption(pkg.get("optimization_summary", ""))

                    covered = pkg.get("covered_keywords", [])
                    missing = pkg.get("truthful_missing_keywords", [])
                    if covered:
                        st.success(f"✅ Covered: {', '.join(covered[:10])}")
                    if missing:
                        st.warning(f"⚠️ Truthfully missing (NOT in resume): {', '.join(missing[:8])}")

                    resume_path = pkg.get("resume_path", "")
                    if resume_path and Path(resume_path).exists():
                        with open(resume_path, "rb") as f:
                            st.download_button(
                                "📥 Download Tailored Resume",
                                f,
                                file_name=Path(resume_path).name,
                                mime="application/pdf",
                                key=f"dl_{item_id}",
                            )

    except Exception as e:
        st.error(f"Resume review error: {e}")
        import traceback; st.code(traceback.format_exc())


# ─────────────────────────────────────────────────────────────────────────────
# Page 4 — Apply Queue
# ─────────────────────────────────────────────────────────────────────────────

def _page_apply_queue():
    st.title("4 · Apply Queue")
    st.caption("Approved jobs only. Applies one by one with your tailored resume and truth-safe answers.")

    try:
        from services.apply_queue_service import (
            get_approved_queue, get_queue_summary, mark_applied, mark_blocked,
            set_job_state, JobQueueState
        )

        approved = get_approved_queue()
        summary = get_queue_summary()

        cols = st.columns(4)
        cols[0].metric("Approved", summary.get("approved_for_apply", 0))
        cols[1].metric("Applied Today", summary.get("applied", 0))
        cols[2].metric("Blocked", summary.get("blocked", 0))
        cols[3].metric("In Queue", len(approved))

        if not approved:
            st.info("No approved jobs in queue. Go to **2 · Review Queue** to approve jobs.")
            return

        st.divider()

        # Show queue
        for item in approved:
            item_id = item["id"]
            with st.container(border=True):
                col1, col2 = st.columns([4, 2])
                col1.markdown(f"**{item.get('job_title')}** @ {item.get('company')}")
                col1.caption(item.get("job_url", ""))
                col2.metric("Fit", f"{item.get('overall_fit_score', 0)}/100")
                col2.metric("ATS", f"{item.get('final_ats_score', item.get('ats_score', 0))}/100")
                col2.caption(f"Package: {item.get('package_status', 'not_generated')}")

        st.divider()

        # Run controls
        col_run, col_dry = st.columns(2)
        if col_run.button("🚀 Apply to All Approved Jobs", type="primary", use_container_width=True):
            _run_apply_queue(approved)

        if col_dry.button("🔍 Dry Run (fill but don't submit)", use_container_width=True):
            _run_apply_queue(approved, dry_run=True)

    except Exception as e:
        st.error(f"Apply queue error: {e}")
        import traceback; st.code(traceback.format_exc())


def _run_apply_queue(items: list[dict], dry_run: bool = False):
    """Process the approved apply queue one by one."""
    from services.apply_queue_service import set_job_state, mark_applied, mark_blocked, JobQueueState

    progress = st.progress(0)
    status_area = st.empty()
    results_log = []

    for i, item in enumerate(items):
        item_id = item["id"]
        job_title = item.get("job_title", "")
        company = item.get("company", "")
        job_url = item.get("job_url", "")

        status_area.info(f"{'[DRY RUN] ' if dry_run else ''}Applying to {job_title} @ {company}…")
        set_job_state(item_id, JobQueueState.APPLYING)

        try:
            result = _apply_single_job(item, dry_run=dry_run)
            if result.get("success"):
                mark_applied(item_id)
                results_log.append({"job": f"{job_title} @ {company}", "status": "✅ Applied" if not dry_run else "🔍 Dry run OK"})
                status_area.success(f"{'[DRY RUN] ' if dry_run else ''}Applied: {job_title} @ {company}")
            else:
                mark_blocked(item_id, result.get("error", "Unknown error"))
                results_log.append({"job": f"{job_title} @ {company}", "status": f"🚫 Blocked: {result.get('error', '')}"})

        except Exception as e:
            mark_blocked(item_id, str(e)[:200])
            results_log.append({"job": f"{job_title} @ {company}", "status": f"❌ Error: {str(e)[:80]}"})

        progress.progress((i + 1) / len(items))
        time.sleep(2)  # Rate limit

    status_area.empty()
    st.success("Queue run complete!")
    for r in results_log:
        st.write(f"{r['status']} — {r['job']}")


def _apply_single_job(item: dict, dry_run: bool = False) -> dict:
    """Apply to a single approved job. Returns {success, error}."""
    try:
        from services.linkedin_browser_automation import apply_to_jobs_payload
        jobs_payload = [{
            "url": item.get("job_url"),
            "title": item.get("job_title"),
            "company": item.get("company"),
            "apply_url": item.get("job_url"),
            "fit_decision": "apply",
            "ats_score": item.get("final_ats_score", item.get("ats_score", 85)),
        }]
        result = apply_to_jobs_payload(
            jobs=jobs_payload,
            dry_run=dry_run,
            shadow_mode=False,
            rate_limit_seconds=5,
            manual_assist=False,
            require_safeguards=True,
        )
        applied = result.get("applied", 0)
        return {"success": applied > 0 or dry_run, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)[:200]}


# ─────────────────────────────────────────────────────────────────────────────
# Page 5 — Tracker
# ─────────────────────────────────────────────────────────────────────────────

def _page_tracker():
    st.title("5 · Tracker")
    st.caption("Full lifecycle view of every job across all phases.")

    try:
        from services.apply_queue_service import get_queue, get_queue_summary

        summary = get_queue_summary()
        _render_queue_summary_badges(summary)
        st.divider()

        # All items
        all_items = get_queue(limit=200)
        if not all_items:
            st.info("No jobs tracked yet. Start with Discovery.")
            return

        # Build display table
        rows = []
        for item in all_items:
            rows.append({
                "Company": item.get("company", ""),
                "Title": item.get("job_title", ""),
                "State": item.get("job_state", ""),
                "Fit": item.get("overall_fit_score", 0),
                "ATS": item.get("ats_score", 0),
                "ATS Final": item.get("final_ats_score", 0),
                "Package": item.get("package_status", "not_generated"),
                "Decision": item.get("user_decision", "pending"),
                "Applied": item.get("application_date", ""),
                "URL": item.get("job_url", ""),
            })

        import pandas as pd
        df = pd.DataFrame(rows)

        # Filter controls
        col1, col2 = st.columns(2)
        state_filter = col1.multiselect(
            "Filter by state",
            options=sorted(df["State"].unique().tolist()),
            default=[],
        )
        if state_filter:
            df = df[df["State"].isin(state_filter)]

        st.dataframe(df, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"Tracker error: {e}")
        import traceback; st.code(traceback.format_exc())


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar status
# ─────────────────────────────────────────────────────────────────────────────

def _render_sidebar_status():
    """Show quick status checklist in sidebar."""
    checks = []

    try:
        from services.profile_service import load_profile, is_auto_apply_ready
        profile = load_profile()
        checks.append(("✅", "Profile loaded") if profile else ("❌", "No profile"))
        if profile:
            checks.append(("✅", "Apply-ready") if is_auto_apply_ready(profile) else ("⚠️", "Profile incomplete"))
    except Exception:
        checks.append(("❌", "Profile error"))

    try:
        from services.resume_package_service import _load_master_resume_text
        text = _load_master_resume_text()
        checks.append(("✅", "Resume loaded") if text else ("❌", "No resume found"))
    except Exception:
        checks.append(("❌", "Resume error"))

    try:
        from services.apply_queue_service import get_queue_summary
        summary = get_queue_summary()
        total = sum(summary.values())
        checks.append(("📋", f"{total} jobs in queue") if total else ("📋", "Queue empty"))
    except Exception:
        pass

    for icon, label in checks:
        st.caption(f"{icon} {label}")


if __name__ == "__main__":
    run()
