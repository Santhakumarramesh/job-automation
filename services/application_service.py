"""
Application service. Log to tracker, load applications.
"""

import os
from services.application_tracker import log_application, load_applications, APPLICATION_FILE

USE_DB = os.getenv("TRACKER_USE_DB", "").lower() in ("1", "true", "yes")


def get_applications():
    """Load application tracker data as DataFrame."""
    return load_applications()


def log_to_tracker(state: dict) -> dict:
    """Log application to tracker. Returns state unchanged."""
    return log_application(state)


def save_tracker_edits(edited_df):
    """Save edited tracker DataFrame (e.g. status updates) to CSV or DB."""
    save_df = edited_df.copy()
    for old, new in [("Company", "company"), ("Position", "position"), ("Status", "status"), ("Job Description", "job_description")]:
        if old in save_df.columns:
            save_df = save_df.rename(columns={old: new})
    if USE_DB:
        try:
            from services.tracker_db import save_applications_db
            save_applications_db(save_df)
        except ImportError:
            save_df.to_csv(APPLICATION_FILE, index=False)
    else:
        save_df.to_csv(APPLICATION_FILE, index=False)
