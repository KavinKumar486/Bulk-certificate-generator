from pathlib import Path
from app.models import Job, JobStatus
from app.schemas import JobCreateRequest, RecipientIn
from app.services.job_service import create_job, process_job


def test_job_status_all_valid(client, auth_headers, db_session):
    payload = {
        "event_name": "FastAPI Masterclass",
        "recipients": [
            {"name": "Alice", "email": "alice@example.com"},
            {"name": "Bob", "email": "bob@example.com"},
        ],
    }
    # TestClient runs background tasks automatically on completion of request
    res = client.post("/v1/jobs", json=payload, headers=auth_headers)
    assert res.status_code == 202
    job_id = res.json()["job_id"]

    # Poll status endpoint
    status_res = client.get(f"/v1/jobs/{job_id}", headers=auth_headers)
    assert status_res.status_code == 200
    data = status_res.json()

    assert data["job_id"] == job_id
    assert data["status"] == "completed"
    assert data["total"] == 2
    assert data["succeeded"] == 2
    assert data["failed"] == 0
    assert data["pending"] == 0
    assert data["completed_at"] is not None
    assert len(data["certificates"]) == 2
    for cert in data["certificates"]:
        assert cert["status"] == "success"
        assert cert["error_message"] is None
        assert cert["download_url"] == f"/v1/jobs/{job_id}/certificates/{cert['id']}/download"


def test_job_status_mixed(client, auth_headers):
    payload = {
        "event_name": "Mixed Event",
        "recipients": [
            {"name": "Charlie", "email": "charlie@example.com"},
            {"name": "", "email": "bad"},  # invalid Level 2
            {"name": "David", "email": "david@example.com"},
        ],
    }
    res = client.post("/v1/jobs", json=payload, headers=auth_headers)
    job_id = res.json()["job_id"]

    status_res = client.get(f"/v1/jobs/{job_id}", headers=auth_headers)
    assert status_res.status_code == 200
    data = status_res.json()

    assert data["status"] == "completed_with_errors"
    assert data["total"] == 3
    assert data["succeeded"] == 2
    assert data["failed"] == 1
    assert data["pending"] == 0

    certs = data["certificates"]
    assert certs[0]["status"] == "success"
    assert certs[0]["download_url"] is not None
    assert certs[1]["status"] == "failed"
    assert certs[1]["download_url"] is None
    assert certs[1]["error_message"] is not None
    assert certs[2]["status"] == "success"
    assert certs[2]["download_url"] is not None


def test_job_status_all_invalid(client, auth_headers):
    payload = {
        "event_name": "Bad Batch",
        "recipients": [
            {"name": ""},
            {"name": "A" * 105},
        ],
    }
    res = client.post("/v1/jobs", json=payload, headers=auth_headers)
    job_id = res.json()["job_id"]

    status_res = client.get(f"/v1/jobs/{job_id}", headers=auth_headers)
    assert status_res.status_code == 200
    data = status_res.json()

    assert data["status"] == "failed"
    assert data["total"] == 2
    assert data["succeeded"] == 0
    assert data["failed"] == 2
    assert data["pending"] == 0


def test_pending_count_mid_processing(client, auth_headers, db_session):
    # Manually create job without background processing to verify pending state
    req = JobCreateRequest(
        event_name="Pending Test",
        recipients=[
            RecipientIn(name="One"),
            RecipientIn(name="Two"),
            RecipientIn(name="Three"),
        ],
    )
    job = create_job(db_session, req)

    # Check status before processing
    status_res = client.get(f"/v1/jobs/{job.id}", headers=auth_headers)
    assert status_res.status_code == 200
    data = status_res.json()
    assert data["status"] == "pending"
    assert data["total"] == 3
    assert data["succeeded"] == 0
    assert data["failed"] == 0
    assert data["pending"] == 3

    # Now run process_job directly
    process_job(job.id)

    # Check status after processing
    status_res = client.get(f"/v1/jobs/{job.id}", headers=auth_headers)
    data = status_res.json()
    assert data["status"] == "completed"
    assert data["pending"] == 0
    assert data["succeeded"] == 3


def test_pagination(client, auth_headers, db_session):
    recipients = [{"name": f"Person {i:02d}"} for i in range(15)]
    req = JobCreateRequest(event_name="Pagination Test", recipients=recipients)
    job = create_job(db_session, req)
    process_job(job.id)

    # Page 1, page_size 5
    p1 = client.get(f"/v1/jobs/{job.id}?page=1&page_size=5", headers=auth_headers).json()
    assert len(p1["certificates"]) == 5
    assert p1["certificates"][0]["recipient_name"] == "Person 00"
    assert p1["certificates"][4]["recipient_name"] == "Person 04"

    # Page 2, page_size 5
    p2 = client.get(f"/v1/jobs/{job.id}?page=2&page_size=5", headers=auth_headers).json()
    assert len(p2["certificates"]) == 5
    assert p2["certificates"][0]["recipient_name"] == "Person 05"
    assert p2["certificates"][4]["recipient_name"] == "Person 09"

    # Page 4, page_size 5 (empty)
    p4 = client.get(f"/v1/jobs/{job.id}?page=4&page_size=5", headers=auth_headers).json()
    assert len(p4["certificates"]) == 0


def test_get_job_unknown_404(client, auth_headers):
    res = client.get("/v1/jobs/00000000-0000-0000-0000-000000000000", headers=auth_headers)
    assert res.status_code == 404
    assert res.json() == {"detail": "Job not found"}


def test_get_job_auth_required(client):
    res = client.get("/v1/jobs/00000000-0000-0000-0000-000000000000")
    assert res.status_code == 401
    assert res.json() == {"detail": "Invalid or missing API key"}
