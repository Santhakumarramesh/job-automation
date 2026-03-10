from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "Job Automation API is active"}

def test_submit_job():
    # Mock data
    job_data = {
        "name": "Test Job",
        "payload": {"url": "https://example.com/job"}
    }
    # Note: This might fail if the user dependency isn't properly handled in test
    # but for a skeleton it's a good place to start.
    response = client.post("/api/jobs", json=job_data)
    assert response.status_code == 202
    assert response.json()["status"] == "accepted"
