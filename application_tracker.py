
import pandas as pd
import os
from datetime import datetime

# Use project root so path works from any cwd
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
APPLICATION_FILE = os.path.join(_SCRIPT_DIR, 'job_applications.csv')

def initialize_tracker():
    """Creates the CSV file with headers if it doesn't exist."""
    if not os.path.exists(APPLICATION_FILE):
        df = pd.DataFrame(columns=[
            'Date Applied',
            'Company',
            'Position',
            'Status',
            'Resume Path',
            'Cover Letter Path',
            'Job Description' # Storing the JD for the interview prep agent
        ])
        df.to_csv(APPLICATION_FILE, index=False)

def log_application(state: dict):
    """Logs a processed job application to the CSV file."""
    initialize_tracker()
    
    new_log = pd.DataFrame([{
        'Date Applied': datetime.now().strftime('%Y-%m-%d'),
        'Company': state.get('target_company', 'N/A'),
        'Position': state.get('target_position', 'N/A'),
        'Status': 'Applied',
        'Resume Path': state.get('final_pdf_path', ''),
        'Cover Letter Path': state.get('cover_letter_pdf_path', ''),
        'Job Description': state.get('job_description', '')
    }])
    
    # Append to the CSV without writing headers every time
    new_log.to_csv(APPLICATION_FILE, mode='a', header=False, index=False)
    print(f"✅ Application for {state.get('target_company')} logged in tracker.")
    return state # Pass through state

def load_applications():
    """Loads all logged applications from the CSV file."""
    initialize_tracker()
    try:
        return pd.read_csv(APPLICATION_FILE)
    except pd.errors.EmptyDataError:
        return pd.DataFrame() # Return empty dataframe if file is empty
