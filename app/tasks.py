from celery import Celery
import uuid
from typing import Any, Dict
import os
from agents.state import AgentState
from agents.job_analyzer import analyze_job_description
from agents.resume_editor import tailor_resume
from agents.cover_letter_generator import generate_cover_letter
from agents.job_guard import guard_job_quality
from agents.humanize_resume import humanize_resume
from agents.humanize_cover_letter import humanize_cover_letter
from agents.file_manager import save_documents
from intelligent_project_generator import intelligent_project_generator

# Get Redis URLs from env or use defaults
REDIS_BROKER = os.getenv("REDIS_BROKER", "redis://localhost:6379/0")
REDIS_BACKEND = os.getenv("REDIS_BACKEND", "redis://localhost:6379/1")

celery = Celery("career_co_pilot_pro", broker=REDIS_BROKER, backend=REDIS_BACKEND)

@celery.task(bind=True, acks_late=True)
def run_job(self, job_name: str, payload: Dict[str, Any], user_id: str):
    """
    Background task to execute job automation agents.
    """
    print(f"🚀 Starting job: {job_name} for user: {user_id}")
    
    # Initialize state from payload
    state: AgentState = payload
    
    # Execute the pipeline (Simplified orchestration from app.py)
    # Note: In a full production setup, this would use the LangGraph workflow
    try:
        # 1. Job Guard
        guard_res = guard_job_quality(state)
        state.update(guard_res)
        if not state.get("is_eligible", True):
            return {"status": "rejected", "reason": state.get("eligibility_reason", "Ineligible")}
            
        # 2. Analyze JD
        analysis_res = analyze_job_description(state)
        state.update(analysis_res)
        
        # 3. Tailor Resume
        tailor_res = tailor_resume(state)
        state.update(tailor_res)
        
        # 4. Humanize Resume
        human_resume_res = humanize_resume(state)
        state.update(human_resume_res)
        
        # 5. Project Generation
        project_res = intelligent_project_generator(state)
        state.update(project_res)
        
        # 6. Cover Letter
        cl_res = generate_cover_letter(state)
        state.update(cl_res)
        
        # 7. Humanize Cover Letter
        human_cl_res = humanize_cover_letter(state)
        state.update(human_cl_res)
        
        # 8. Save Documents
        file_res = save_documents(state)
        state.update(file_res)
        
        return {
            "status": "success", 
            "job_name": job_name, 
            "final_pdf_path": state.get("final_pdf_path"),
            "cover_letter_pdf_path": state.get("cover_letter_pdf_path")
        }
    except Exception as e:
        print(f"❌ Job error: {e}")
        return {"status": "error", "message": str(e)}

def enqueue_job(name: str, payload: Dict[str, Any], user_id: str) -> str:
    """Enqueue a new job and return its UUID."""
    job_id = str(uuid.uuid4())
    run_job.apply_async(args=(name, payload, user_id), task_id=job_id)
    return job_id
