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
    assert db_job.status == JobStatus.PENDING
    assert db_job.total == 2
    assert db_job.succeeded == 0
    assert db_job.failed == 0

    assert len(db_job.certificates) == 2
    for cert in db_job.certificates:
        assert cert.status == CertificateStatus.PENDING
        assert cert.file_path is None
        assert cert.error_message is None

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
