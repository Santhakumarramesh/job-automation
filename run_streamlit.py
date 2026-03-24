"""
Career Co-Pilot Pro - Streamlit entry point.
Delegates to ui/streamlit_app for the full interface.

(Run with: streamlit run run_streamlit.py)
"""

from dotenv import load_dotenv

load_dotenv()

from services.startup_checks import run_startup_checks

run_startup_checks("streamlit")

from ui.streamlit_app import run

run()
