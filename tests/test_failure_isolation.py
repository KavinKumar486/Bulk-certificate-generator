from pathlib import Path
import pytest
from app.models import Certificate, CertificateStatus, Job, JobStatus
from app.schemas import JobCreateRequest, RecipientIn
from app.services import pdf_service
from app.services.job_service import create_job, process_job


def test_failure_isolation_render_exception(client, auth_headers, monkeypatch, db_session):
    original_render = pdf_service.render_certificate

    def flaky_render(cert, event_name, out_path):
        name = getattr(cert, "recipient_name", "")
        if name == "Failing Recipient":
            raise RuntimeError("Simulated render engine crash for specific recipient")
        return original_render(cert, event_name, out_path)

    monkeypatch.setattr(pdf_service, "render_certificate", flaky_render)

    payload = {
        "event_name": "Resilience Test Event",
        "recipients": [
            {"name": "Good Recipient 1"},
            {"name": "Failing Recipient"},
            {"name": "Good Recipient 2"},
        ],
    }

    res = client.post("/v1/jobs", json=payload, headers=auth_headers)
    assert res.status_code == 202
    job_id = res.json()["job_id"]

    status_res = client.get(f"/v1/jobs/{job_id}", headers=auth_headers)
    assert status_res.status_code == 200
    data = status_res.json()

    assert data["status"] == "completed_with_errors"
    assert data["total"] == 3
    assert data["succeeded"] == 2
    assert data["failed"] == 1

    certs = data["certificates"]
    # Check Good Recipient 1
    assert certs[0]["recipient_name"] == "Good Recipient 1"
    assert certs[0]["status"] == "success"
    assert certs[0]["download_url"] is not None

    # Check Failing Recipient
    assert certs[1]["recipient_name"] == "Failing Recipient"
    assert certs[1]["status"] == "failed"
    assert "Simulated render engine crash" in certs[1]["error_message"]
    assert certs[1]["download_url"] is None

    # Check Good Recipient 2
    assert certs[2]["recipient_name"] == "Good Recipient 2"
    assert certs[2]["status"] == "success"
    assert certs[2]["download_url"] is not None

    # Verify files on disk
    db_certs = db_session.query(Certificate).filter_by(job_id=job_id).all()
    for c in db_certs:
        if c.status == CertificateStatus.SUCCESS:
            assert Path(c.file_path).exists()
        else:
            assert c.file_path is None


def test_failure_isolation_level2_validation_failure(client, auth_headers, db_session):
    payload = {
        "event_name": "Validation Isolation",
        "recipients": [
            {"name": "Asha Rao"},
            {"name": "   "},  # Blank name -> Level 2 failure
            {"name": "Bob Smith"},
        ],
    }
    res = client.post("/v1/jobs", json=payload, headers=auth_headers)
    assert res.status_code == 202
    job_id = res.json()["job_id"]

    status_res = client.get(f"/v1/jobs/{job_id}", headers=auth_headers)
    data = status_res.json()

    assert data["status"] == "completed_with_errors"
    assert data["succeeded"] == 2
    assert data["failed"] == 1

    certs = data["certificates"]
    assert certs[1]["status"] == "failed"
    assert "Recipient name is required" in certs[1]["error_message"]


def test_process_job_rerun_idempotency(db_session, temp_storage):
    req = JobCreateRequest(
        event_name="Rerun Test",
        recipients=[
            RecipientIn(name="User A"),
            RecipientIn(name="User B"),
        ],
    )
    job = create_job(db_session, req)

    # First run
    process_job(job.id)
    db_session.expire_all()

    db_job = db_session.query(Job).filter_by(id=job.id).first()
    assert db_job.status == JobStatus.COMPLETED
    assert db_job.succeeded == 2
    assert db_job.failed == 0

    certs = db_session.query(Certificate).filter_by(job_id=job.id).all()
    file_paths_first_run = [c.file_path for c in certs]
    assert len(file_paths_first_run) == 2
    for p in file_paths_first_run:
        assert Path(p).exists()

    # Re-run process_job
    process_job(job.id)

    db_session.refresh(db_job)
    # Counters should NOT double count
    assert db_job.status == JobStatus.COMPLETED
    assert db_job.succeeded == 2
    assert db_job.failed == 0

    certs_after = db_session.query(Certificate).filter_by(job_id=job.id).all()
    assert len(certs_after) == 2
    for c in certs_after:
        assert c.status == CertificateStatus.SUCCESS
