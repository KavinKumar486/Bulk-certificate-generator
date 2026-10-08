import io
import zipfile
from pypdf import PdfReader
from app.models import Certificate, CertificateStatus, Job, JobStatus
from app.schemas import JobCreateRequest, RecipientIn
from app.services.job_service import create_job, process_job


def test_download_single_pdf_success(client, auth_headers):
    payload = {
        "event_name": "Download Test",
        "recipients": [{"name": "Asha Rao", "course": "Python"}],
    }
    create_res = client.post("/v1/jobs", json=payload, headers=auth_headers)
    assert create_res.status_code == 202
    job_id = create_res.json()["job_id"]

    status_res = client.get(f"/v1/jobs/{job_id}", headers=auth_headers)
    cert_id = status_res.json()["certificates"][0]["id"]
    download_url = status_res.json()["certificates"][0]["download_url"]
    assert download_url == f"/v1/jobs/{job_id}/certificates/{cert_id}/download"

    # Download certificate
    dl_res = client.get(download_url, headers=auth_headers)
    assert dl_res.status_code == 200
    assert dl_res.headers["content-type"] == "application/pdf"
    assert dl_res.content.startswith(b"%PDF")
    assert "attachment" in dl_res.headers.get("content-disposition", "")
    assert f"Asha_Rao_{cert_id[:8]}.pdf" in dl_res.headers.get("content-disposition", "")

    # Validate PDF content
    reader = PdfReader(io.BytesIO(dl_res.content))
    assert len(reader.pages) == 1
    assert "Asha Rao" in reader.pages[0].extract_text()


def test_download_failed_certificate_returns_409(client, auth_headers):
    payload = {
        "event_name": "Failure Test",
        "recipients": [
            {"name": "Valid Recipient"},
            {"name": "   "},  # Blank name -> Level 2 failure
        ],
    }
    create_res = client.post("/v1/jobs", json=payload, headers=auth_headers)
    job_id = create_res.json()["job_id"]

    status_res = client.get(f"/v1/jobs/{job_id}", headers=auth_headers)
    certs = status_res.json()["certificates"]
    failed_cert = next(c for c in certs if c["status"] == "failed")

    dl_res = client.get(
        f"/v1/jobs/{job_id}/certificates/{failed_cert['id']}/download",
        headers=auth_headers,
    )
    assert dl_res.status_code == 409
    assert "Certificate generation failed" in dl_res.json()["detail"]
    assert "Recipient name is required" in dl_res.json()["detail"]


def test_download_pending_certificate_returns_409(client, auth_headers, db_session):
    req = JobCreateRequest(
        event_name="Pending Download Test",
        recipients=[RecipientIn(name="Pending Person")],
    )
    job = create_job(db_session, req)
    cert = job.certificates[0]

    dl_res = client.get(
        f"/v1/jobs/{job.id}/certificates/{cert.id}/download",
        headers=auth_headers,
    )
    assert dl_res.status_code == 409
    assert dl_res.json()["detail"] == "Certificate generation is still pending"


def test_download_unknown_job_or_cert_returns_404(client, auth_headers, db_session):
    # Unknown job
    res1 = client.get(
        "/v1/jobs/nonexistent-job-id/certificates/nonexistent-cert-id/download",
        headers=auth_headers,
    )
    assert res1.status_code == 404
    assert res1.json()["detail"] == "Job not found"

    # Known job, unknown cert
    req = JobCreateRequest(
        event_name="Known Job Test",
        recipients=[RecipientIn(name="User")],
    )
    job = create_job(db_session, req)

    res2 = client.get(
        f"/v1/jobs/{job.id}/certificates/nonexistent-cert-id/download",
        headers=auth_headers,
    )
    assert res2.status_code == 404
    assert res2.json()["detail"] == "Certificate not found or does not belong to this job"


def test_download_cert_from_different_job_returns_404(client, auth_headers, db_session):
    req1 = JobCreateRequest(event_name="Job 1", recipients=[RecipientIn(name="User 1")])
    job1 = create_job(db_session, req1)

    req2 = JobCreateRequest(event_name="Job 2", recipients=[RecipientIn(name="User 2")])
    job2 = create_job(db_session, req2)

    cert2 = job2.certificates[0]

    # Try downloading cert2 under job1 URL
    res = client.get(
        f"/v1/jobs/{job1.id}/certificates/{cert2.id}/download",
        headers=auth_headers,
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "Certificate not found or does not belong to this job"


def test_download_zip_success(client, auth_headers):
    payload = {
        "event_name": "ZIP Test",
        "recipients": [
            {"name": "Alice Smith"},
            {"name": "../evil/path/name"},  # Path traversal attempt in name
            {"name": "   "},  # Invalid Level 2 -> fails
        ],
    }
    create_res = client.post("/v1/jobs", json=payload, headers=auth_headers)
    job_id = create_res.json()["job_id"]

    zip_res = client.get(f"/v1/jobs/{job_id}/download", headers=auth_headers)
    assert zip_res.status_code == 200
    assert zip_res.headers["content-type"] == "application/zip"
    assert f"job_{job_id}_certificates.zip" in zip_res.headers.get("content-disposition", "")

    # Inspect zip contents
    zf = zipfile.ZipFile(io.BytesIO(zip_res.content))
    file_list = zf.namelist()
    # Exactly 2 successful files, none for the failed recipient
    assert len(file_list) == 2

    # Verify filenames are safely sanitized (no ../ or path traversal)
    assert any(name.startswith("Alice_Smith_") and name.endswith(".pdf") for name in file_list)
    assert any(name.startswith("evil_path_name_") and name.endswith(".pdf") for name in file_list)
    assert not any("../" in name or "..\\" in name for name in file_list)

    # Verify each PDF in ZIP is valid
    for file_name in file_list:
        content = zf.read(file_name)
        assert content.startswith(b"%PDF")


def test_download_zip_pending_or_processing_job_returns_409(client, auth_headers, db_session):
    req = JobCreateRequest(
        event_name="Pending ZIP Test",
        recipients=[RecipientIn(name="User Pending")],
    )
    job = create_job(db_session, req)

    res = client.get(f"/v1/jobs/{job.id}/download", headers=auth_headers)
    assert res.status_code == 409
    assert "Job is still pending" in res.json()["detail"]


def test_download_zip_zero_successes_returns_409(client, auth_headers):
    payload = {
        "event_name": "Zero Successes Event",
        "recipients": [{"name": ""}, {"name": "   "}],
    }
    create_res = client.post("/v1/jobs", json=payload, headers=auth_headers)
    job_id = create_res.json()["job_id"]

    res = client.get(f"/v1/jobs/{job_id}/download", headers=auth_headers)
    assert res.status_code == 409
    assert res.json()["detail"] == "No successful certificates available to download for this job."


def test_download_zip_unknown_job_returns_404(client, auth_headers):
    res = client.get(
        "/v1/jobs/00000000-0000-0000-0000-000000000000/download",
        headers=auth_headers,
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "Job not found"


def test_download_endpoints_require_auth(client, auth_headers):
    payload = {
        "event_name": "Auth Download Test",
        "recipients": [{"name": "Asha Rao"}],
    }
    create_res = client.post("/v1/jobs", json=payload, headers=auth_headers)
    job_id = create_res.json()["job_id"]
    status_res = client.get(f"/v1/jobs/{job_id}", headers=auth_headers)
    cert_id = status_res.json()["certificates"][0]["id"]

    # 1. Single PDF download without key -> 401
    res1 = client.get(f"/v1/jobs/{job_id}/certificates/{cert_id}/download")
    assert res1.status_code == 401
    assert res1.json() == {"detail": "Invalid or missing API key"}

    # Single PDF download with bad key -> 401
    res1_bad = client.get(
        f"/v1/jobs/{job_id}/certificates/{cert_id}/download",
        headers={"X-API-Key": "wrong-key"},
    )
    assert res1_bad.status_code == 401
    assert res1_bad.json() == {"detail": "Invalid or missing API key"}

    # 2. ZIP download without key -> 401
    res2 = client.get(f"/v1/jobs/{job_id}/download")
    assert res2.status_code == 401
    assert res2.json() == {"detail": "Invalid or missing API key"}

    # ZIP download with bad key -> 401
    res2_bad = client.get(
        f"/v1/jobs/{job_id}/download",
        headers={"X-API-Key": "wrong-key"},
    )
    assert res2_bad.status_code == 401
    assert res2_bad.json() == {"detail": "Invalid or missing API key"}
