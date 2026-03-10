from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
from .tasks import enqueue_job
from .auth import get_current_user
from typing import Dict, Any

app = FastAPI(title="Job Automation API")

class JobRequest(BaseModel):
    name: str = Field(..., min_length=1)
    payload: Dict[str, Any]

@app.get("/")
def read_root():
    return {"status": "Job Automation API is active"}

@app.post("/api/jobs", status_code=202)
def submit_job(req: JobRequest, user=Depends(get_current_user)):
    # Basic server-side validation
    if len(req.name) > 100:
        raise HTTPException(400, "Job name too long")
    
    job_id = enqueue_job(req.name, req.payload, user.id)
    return {"job_id": job_id, "status": "accepted"}
