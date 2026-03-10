"""
Excel Sync - Updates dashboard_data.xlsx on every change.
Call from log_application, ATS checker, or dashboard.
"""
import os
import pandas as pd
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

def _find_csv():
    for p in [BASE / "job applications automation" / "job_applications.csv",
              BASE / "job applications automation " / "job_applications.csv"]:
        if p.exists():
            return p
    return BASE / "job applications automation" / "job_applications.csv"

CSV_PATH = _find_csv()
EXCEL_PATH = BASE / "dashboard" / "dashboard_data.xlsx"
ATS_REPORTS_DIR = BASE / "dashboard" / "ats_reports"


def sync_all_to_excel():
    """Merge applications, ATS reports, and updates into master Excel."""
    os.makedirs(EXCEL_PATH.parent, exist_ok=True)
    os.makedirs(ATS_REPORTS_DIR, exist_ok=True)

    # 1. Applications
    apps = pd.DataFrame()
    if CSV_PATH.exists():
        apps = pd.read_csv(CSV_PATH)

    # 2. ATS Summary
    ats_rows = []
    if not apps.empty and "ats_score" in apps.columns:
        for _, row in apps.iterrows():
            try:
                score = pd.to_numeric(row.get("ats_score"), errors="coerce")
                if pd.notna(score):
                    ats_rows.append({
                        "applied_at": row.get("applied_at", ""),
                        "job_title": row.get("job_title", ""),
                        "company": row.get("company", ""),
                        "ats_score": int(score),
                        "resume_path": row.get("resume_path", ""),
                        "status": row.get("status", ""),
                    })
            except (ValueError, TypeError):
                pass
    ats_df = pd.DataFrame(ats_rows) if ats_rows else pd.DataFrame(columns=["applied_at", "job_title", "company", "ats_score", "resume_path", "status"])

    # 3. ATS Breakdown (from report files)
    breakdown_rows = []
    for f in ATS_REPORTS_DIR.glob("*.xlsx"):
        try:
            df = pd.read_excel(f, sheet_name="ATS_Score")
            for _, row in df.iterrows():
                breakdown_rows.append({
                    "file": f.name,
                    "check_date": row.get("Check Date", ""),
                    "ats_score": row.get("ATS Score", 0),
                    "keyword_score": row.get("Keyword Score", 0),
                    "formatting_score": row.get("Formatting Score", 0),
                    "structure_score": row.get("Structure Score", 0),
                })
        except Exception:
            pass
    breakdown_df = pd.DataFrame(breakdown_rows) if breakdown_rows else pd.DataFrame()

    # 4. Updates log
    updates = []
    if not apps.empty:
        for _, row in apps.iterrows():
            updates.append({
                "timestamp": row.get("applied_at", ""),
                "event": "Application",
                "details": f"{row.get('job_title', '')} at {row.get('company', '')} | ATS: {row.get('ats_score', 'N/A')}",
            })
    updates.append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "event": "Excel sync",
        "details": f"Applications: {len(apps)}, ATS records: {len(ats_df)}",
    })
    updates_df = pd.DataFrame(updates)

    # Write Excel
    with pd.ExcelWriter(EXCEL_PATH, engine="openpyxl") as writer:
        apps.to_excel(writer, sheet_name="Applications", index=False)
        ats_df.to_excel(writer, sheet_name="ATS_Score", index=False)
        if not breakdown_df.empty:
            breakdown_df.to_excel(writer, sheet_name="ATS_Breakdown", index=False)
        updates_df.to_excel(writer, sheet_name="Updates", index=False)

    return str(EXCEL_PATH)


if __name__ == "__main__":
    path = sync_all_to_excel()
    print(f"Synced to {path}")
