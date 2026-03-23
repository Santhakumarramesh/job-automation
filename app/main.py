from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
from .tasks import enqueue_job
from .auth import get_current_user
from typing import Dict, Any

app = FastAPI(title="Job Automation API")

class JobRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    payload: Dict[str, Any] = Field(default_factory=dict)


@app.get("/")
def read_root():
    return {"status": "Job Automation API is active"}


@app.get("/health")
def health():
    """Liveness: service is running."""
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Readiness: service can accept work."""
    return {"status": "ready"}


@app.post("/api/jobs", status_code=202)
def submit_job(req: JobRequest, user=Depends(get_current_user)):
    job_id = enqueue_job(req.name, req.payload, user.id)
    return {"job_id": job_id, "status": "accepted"}


@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str, user=Depends(get_current_user)):
    """Get job status. Returns pending/done/failed when available."""
    try:
        from .tasks import get_job_status as _get
        status = _get(job_id)
        return {"job_id": job_id, "status": status}
    except Exception as e:
        raise HTTPException(500, str(e)[:200])
