"""
Career Co-Pilot Pro — Streamlit entry point.

APP_MODE routing:
  candidate  (default) → ui/candidate_app.py  — guided 7-stage workflow for job seekers
  operator              → ui/operator_app.py   — full operator cockpit (batch, API console, admin)

Usage:
  streamlit run run_streamlit.py                        # candidate mode (default)
  APP_MODE=operator streamlit run run_streamlit.py      # operator mode
  APP_MODE=candidate streamlit run run_streamlit.py     # explicit candidate mode
"""

import os
from dotenv import load_dotenv

load_dotenv()

from services.startup_checks import run_startup_checks

run_startup_checks("streamlit")

_mode = os.getenv("APP_MODE", "candidate").strip().lower()

if _mode == "operator":
    from ui.operator_app import run
else:
    from ui.candidate_app import run

run()
