# Job Apply Dashboard

User-friendly dashboard for ATS scores, applications, before/after resumes, and live Excel sync.

## Run

```bash
cd dashboard
streamlit run app.py
```

Open http://localhost:8501

## Features

- **ATS Score** – Latest and average scores
- **Applications** – Table of all logged applications
- **Before/After** – Base resume vs tailored resume
- **ATS Checker Code** – View enhanced_ats_checker.py logic
- **Project Updates** – Activity log
- **Excel Sync** – `dashboard_data.xlsx` updates on every change (applications, ATS reports)

## Excel Output

`dashboard_data.xlsx` contains:
- **Applications** – Full application log
- **ATS_Score** – ATS scores per application
- **ATS_Breakdown** – Detailed breakdown (keyword, formatting, structure)
- **Updates** – Timestamped events
