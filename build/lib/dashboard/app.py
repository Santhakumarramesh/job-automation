"""
Job Apply Dashboard - ATS Score, Applications, Before/After, Live Updates.
Unique dark theme with live Excel sync.
"""
import os
import sys
import pandas as pd
import streamlit as st
from datetime import datetime
from pathlib import Path

# Paths - support both with/without trailing space in folder names
BASE = Path(__file__).resolve().parent.parent
def _find_csv():
    for p in [BASE / "job applications automation" / "job_applications.csv",
              BASE / "job applications automation " / "job_applications.csv"]:
        if p.exists():
            return p
    return BASE / "job applications automation" / "job_applications.csv"
CSV_PATH = _find_csv()
EXCEL_PATH = BASE / "dashboard" / "dashboard_data.xlsx"
ATS_REPORTS = BASE / "dashboard" / "ats_reports"
CANDIDATE_RESUMES = BASE / "candidate_resumes"

st.set_page_config(
    page_title="Job Apply Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS - unique dark editorial style
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
    --bg-dark: #0a0a0f;
    --bg-card: #12121a;
    --accent: #f59e0b;
    --accent-dim: #d97706;
    --text: #e4e4e7;
    --text-muted: #71717a;
    --success: #22c55e;
    --warning: #eab308;
}

.stApp { background: var(--bg-dark) !important; }
.main .block-container { padding: 2rem 3rem; max-width: 1400px; }

h1, h2, h3 { font-family: 'Outfit', sans-serif !important; font-weight: 600 !important; }
p, span, div { font-family: 'Outfit', sans-serif !important; }
code, pre { font-family: 'JetBrains Mono', monospace !important; }

.metric-card {
    background: linear-gradient(135deg, var(--bg-card) 0%, #1a1a24 100%);
    border: 1px solid rgba(245, 158, 11, 0.15);
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1rem;
    box-shadow: 0 4px 24px rgba(0,0,0,0.3);
}

.ats-gauge {
    font-size: 3.5rem;
    font-weight: 700;
    color: var(--accent);
    text-align: center;
    font-family: 'Outfit', sans-serif;
}

.ats-label { color: var(--text-muted); font-size: 0.9rem; text-transform: uppercase; letter-spacing: 0.1em; }

.before-after-box {
    background: var(--bg-card);
    border-radius: 8px;
    padding: 1rem;
    border-left: 4px solid var(--accent);
    font-size: 0.85rem;
    max-height: 200px;
    overflow-y: auto;
}

.update-log { font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; color: var(--text-muted); }

.stDataFrame { border-radius: 8px; overflow: hidden; }
div[data-testid="stDataFrame"] { border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; }
</style>
""", unsafe_allow_html=True)


def load_applications():
    """Load job applications from CSV."""
    if CSV_PATH.exists():
        df = pd.read_csv(CSV_PATH)
        return df
    return pd.DataFrame()


def load_ats_reports():
    """Load ATS check reports from Excel files."""
    reports = []
    if ATS_REPORTS.exists():
        for f in ATS_REPORTS.glob("*.xlsx"):
            try:
                xl = pd.ExcelFile(f)
                for sheet in xl.sheet_names:
                    df = pd.read_excel(f, sheet_name=sheet)
                    reports.append({"file": f.name, "sheet": sheet, "data": df})
            except Exception:
                pass
    return reports


def sync_to_excel():
    """Sync all data to master Excel file."""
    os.makedirs(EXCEL_PATH.parent, exist_ok=True)
    apps = load_applications()
    with pd.ExcelWriter(EXCEL_PATH, engine="openpyxl") as writer:
        apps.to_excel(writer, sheet_name="Applications", index=False)
        # ATS summary from applications
        if not apps.empty and "ats_score" in apps.columns:
            ats_summary = apps[["applied_at", "job_title", "company", "ats_score", "status"]].copy()
            ats_summary.to_excel(writer, sheet_name="ATS_Summary", index=False)
        # Project updates log
        updates = pd.DataFrame({
            "timestamp": [datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            "event": ["Dashboard sync"],
            "details": [f"Applications: {len(apps)}, Excel updated"]
        })
        updates.to_excel(writer, sheet_name="Updates", index=False)
    return EXCEL_PATH


def get_latest_ats_score():
    """Get latest ATS score from applications or reports."""
    apps = load_applications()
    if not apps.empty and "ats_score" in apps.columns:
        scores = pd.to_numeric(apps["ats_score"], errors="coerce").dropna()
        if len(scores) > 0:
            return int(scores.iloc[-1]), int(scores.mean())
    return None, None


def get_before_after_resumes():
    """Get base and tailored resume for before/after view."""
    base_path = CANDIDATE_RESUMES / "Santhakumar_Base_Resume.md"
    tailored = list(CANDIDATE_RESUMES.glob("resume_*.md"))
    base_text = ""
    after_text = ""
    if base_path.exists():
        base_text = base_path.read_text(encoding="utf-8")
    if tailored:
        latest = max(tailored, key=lambda p: p.stat().st_mtime)
        after_text = latest.read_text(encoding="utf-8")
    return base_text, after_text


# Sidebar
with st.sidebar:
    st.markdown("## 📊 Dashboard")
    if st.button("🔄 Sync to Excel", use_container_width=True):
        p = sync_to_excel()
        st.success(f"Saved to {p.name}")
    st.markdown("---")
    st.markdown("**Data sources**")
    st.caption(f"Applications: {CSV_PATH}")
    st.caption(f"Excel: {EXCEL_PATH}")

# Main content
st.markdown("# Job Apply Dashboard")
st.caption("ATS scores • Applications • Before/After • Live updates")

# Metrics row
col1, col2, col3, col4 = st.columns(4)
apps = load_applications()
latest_ats, avg_ats = get_latest_ats_score()

with col1:
    st.markdown('<div class="metric-card"><div class="ats-label">Latest ATS</div><div class="ats-gauge">' + (str(latest_ats) if latest_ats is not None else "—") + '</div></div>', unsafe_allow_html=True)
with col2:
    st.markdown('<div class="metric-card"><div class="ats-label">Avg ATS</div><div class="ats-gauge">' + (str(int(avg_ats)) if avg_ats is not None else "—") + '</div></div>', unsafe_allow_html=True)
with col3:
    st.markdown(f'<div class="metric-card"><div class="ats-label">Applications</div><div class="ats-gauge">{len(apps)}</div></div>', unsafe_allow_html=True)
with col4:
    applied = len(apps[apps["status"] == "Applied"]) if not apps.empty and "status" in apps.columns else 0
    st.markdown(f'<div class="metric-card"><div class="ats-label">Applied</div><div class="ats-gauge">{applied}</div></div>', unsafe_allow_html=True)

# Applications table
st.markdown("## Applications")
if not apps.empty:
    st.dataframe(apps, use_container_width=True, hide_index=True)
else:
    st.info("No applications yet. Run the job agent to start applying.")

# Before / After
st.markdown("## Resume: Before vs After ATS Optimization")
base_text, after_text = get_before_after_resumes()
bc1, bc2 = st.columns(2)
with bc1:
    st.markdown("**Before** (base resume)")
    st.markdown(f'<div class="before-after-box"><pre>{base_text[:2000] or "No base resume found."}</pre></div>', unsafe_allow_html=True)
with bc2:
    st.markdown("**After** (tailored for job)")
    st.markdown(f'<div class="before-after-box"><pre>{after_text[:2000] if after_text else "No tailored resume yet."}</pre></div>', unsafe_allow_html=True)

# ATS Checker code
st.markdown("## ATS Checker: Code Overview")
with st.expander("Enhanced ATS Checker - Scoring Logic"):
    ats_code = (BASE / "enhanced_ats_checker.py").read_text(encoding="utf-8") if (BASE / "enhanced_ats_checker.py").exists() else "# File not found"
    st.code(ats_code[:2500] + "\n# ... (truncated)" if len(ats_code) > 2500 else ats_code, language="python")

# Project updates
st.markdown("## Project Updates")
updates_data = []
if apps.empty is False and "applied_at" in apps.columns:
    for _, row in apps.iterrows():
        updates_data.append({"Time": row.get("applied_at", ""), "Event": "Application", "Details": f"{row.get('job_title', '')} at {row.get('company', '')}"})
updates_data.append({"Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Event": "Dashboard view", "Details": "Page loaded"})
st.dataframe(pd.DataFrame(updates_data[-20:]), use_container_width=True, hide_index=True)

# Auto-sync Excel on load
sync_to_excel()
