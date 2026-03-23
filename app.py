"""
Career Co-Pilot Pro - Thin entry point.
Delegates to ui/streamlit_app for the full Streamlit interface.
"""

from dotenv import load_dotenv
from ui.streamlit_app import run

load_dotenv()
run()
