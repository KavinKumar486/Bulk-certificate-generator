from app.models import CertificateStatus, Job, JobStatus


def test_create_job_success(client, auth_headers, db_session):
    payload = {
        "event_name": "PyCon Workshop 2026",
        "recipients": [
            {
                "name": "Asha Rao",
                "email": "asha@example.com",
                "course": "FastAPI 101",
                "date": "2026-10-01",
            },
            {
                "name": "Bob Smith",
                "email": "bob@example.com",
                "course": "Docker 101",
                "date": "2026-10-02",
            },
        ],
    }

    response = client.post("/v1/jobs", json=payload, headers=auth_headers)
    assert response.status_code == 202
    data = response.json()

    assert "job_id" in data
    assert data["status"] == "pending"
    assert data["total"] == 2

    job_id = data["job_id"]
    db_job = db_session.query(Job).filter_by(id=job_id).first()
    assert db_job is not None
    assert db_job.event_name == "PyCon Workshop 2026"
    assert db_job.total == 2
    # In TestClient, registered BackgroundTasks complete before response context exits
    assert db_job.status == JobStatus.COMPLETED
    assert db_job.succeeded == 2
    assert db_job.failed == 0

    assert len(db_job.certificates) == 2
    for cert in db_job.certificates:
        assert cert.status == CertificateStatus.SUCCESS

    assert db_job.certificates[0].recipient_name == "Asha Rao"
    assert db_job.certificates[0].course == "FastAPI 101"
    assert db_job.certificates[1].recipient_name == "Bob Smith"


def test_create_job_auth_failure(client):
    payload = {
        "event_name": "Workshop",
        "recipients": [{"name": "Asha"}],
    }

    # Missing API Key
    res_no_key = client.post("/v1/jobs", json=payload)
    assert res_no_key.status_code == 401

    # Invalid API Key
    res_bad_key = client.post("/v1/jobs", json=payload, headers={"X-API-Key": "wrong"})
    assert res_bad_key.status_code == 401


def test_create_job_end_to_end_files_on_disk(client, auth_headers, db_session):
    payload = {
        "event_name": "End To End Test",
        "recipients": [
            {"name": "Dev One", "email": "dev1@example.com", "course": "Python", "date": "2026-10-08"},
            {"name": "Dev Two", "email": "dev2@example.com", "course": "FastAPI", "date": "2026-10-08"},
        ],
    }
    response = client.post("/v1/jobs", json=payload, headers=auth_headers)
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    # Poll status endpoint
    status_res = client.get(f"/v1/jobs/{job_id}", headers=auth_headers)
    assert status_res.status_code == 200
    data = status_res.json()
    assert data["status"] == "completed"
    assert data["succeeded"] == 2

    # Query DB and confirm PDF files exist on disk
    from pathlib import Path
    from app.models import Certificate
    certs = db_session.query(Certificate).filter_by(job_id=job_id).all()
    assert len(certs) == 2
    for cert in certs:
        assert cert.file_path is not None
        p = Path(cert.file_path)
        assert p.exists()
        assert p.stat().st_size > 0
        with open(p, "rb") as f:
            assert f.read(4) == b"%PDF"

