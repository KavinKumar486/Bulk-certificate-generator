import io
from pathlib import Path
import re
import zipfile
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth import verify_api_key
from app.db import get_db
from app.models import Certificate, CertificateStatus, Job, JobStatus
from app.schemas import (
    CertificateItemResponse,
    JobCreateRequest,
    JobCreateResponse,
    JobDetailResponse,
)
from app.services.job_service import create_job, process_job

router = APIRouter(
    prefix="/v1/jobs",
    tags=["jobs"],
    dependencies=[Depends(verify_api_key)],
)


def sanitize_filename(name: str) -> str:
    """
    Sanitizes user-provided string for safe inclusion in filenames.
    Prevents path traversal (e.g. '../') and illegal filesystem characters.
    """
    if not name:
        return "recipient"
    clean = name.replace("/", "_").replace("\\", "_").replace("..", "_")
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", clean)
    clean = clean.strip(". ")
    clean = re.sub(r"[\s_]+", "_", clean).strip("_")
    return clean or "recipient"


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=JobCreateResponse)
def create_job_endpoint(
    request: JobCreateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    job = create_job(db, request)
    background_tasks.add_task(process_job, job.id)
    return JobCreateResponse(
        job_id=job.id,
        status=job.status.value if hasattr(job.status, "value") else str(job.status),
        total=job.total,
    )


@router.get("/test", include_in_schema=False)
def test_auth():
    return {"status": "ok"}


@router.get("/{job_id}/download")
def download_job_zip(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter_by(id=job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    if job.status in (JobStatus.PENDING, JobStatus.PROCESSING):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job is still {job.status.value}. ZIP download is only available when processing is complete.",
        )

    successful_certs = (
        db.query(Certificate)
        .filter_by(job_id=job.id, status=CertificateStatus.SUCCESS)
        .order_by(Certificate.created_at.asc())
        .all()
    )

    if not successful_certs:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No successful certificates available to download for this job.",
        )

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for cert in successful_certs:
            if cert.file_path and Path(cert.file_path).exists():
                safe_name = sanitize_filename(cert.recipient_name)
                entry_name = f"{safe_name}_{cert.id[:8]}.pdf"
                zf.write(cert.file_path, arcname=entry_name)

    zip_buffer.seek(0)
    zip_bytes = zip_buffer.getvalue()

    headers = {
        "Content-Disposition": f'attachment; filename="job_{job.id}_certificates.zip"'
    }
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers=headers,
    )


@router.get("/{job_id}/certificates/{cert_id}/download")
def download_single_certificate(job_id: str, cert_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter_by(id=job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    cert = db.query(Certificate).filter_by(id=cert_id, job_id=job_id).first()
    if not cert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certificate not found or does not belong to this job",
        )

    if cert.status == CertificateStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Certificate generation is still pending",
        )
    if cert.status == CertificateStatus.PROCESSING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Certificate is currently processing",
        )
    if cert.status == CertificateStatus.FAILED:
        err_msg = cert.error_message or "Unknown failure"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Certificate generation failed: {err_msg}",
        )

    if not cert.file_path or not Path(cert.file_path).exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certificate PDF file not found on disk",
        )

    safe_name = sanitize_filename(cert.recipient_name)
    download_filename = f"{safe_name}_{cert.id[:8]}.pdf"

    return FileResponse(
        path=cert.file_path,
        media_type="application/pdf",
        filename=download_filename,
    )


@router.get("/{job_id}", response_model=JobDetailResponse)
def get_job_status(
    job_id: str,
    page: int = Query(1, ge=1, description="Page number, 1-indexed"),
    page_size: int = Query(100, ge=1, le=500, description="Items per page, max 500"),
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter_by(id=job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    offset = (page - 1) * page_size
    certs_page = (
        db.query(Certificate)
        .filter_by(job_id=job.id)
        .order_by(Certificate.created_at.asc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    cert_items = []
    for c in certs_page:
        c_status = c.status.value if hasattr(c.status, "value") else str(c.status)
        download_url = (
            f"/v1/jobs/{job.id}/certificates/{c.id}/download"
            if c_status == CertificateStatus.SUCCESS.value
            else None
        )
        cert_items.append(
            CertificateItemResponse(
                id=c.id,
                recipient_name=c.recipient_name,
                status=c_status,
                error_message=c.error_message,
                download_url=download_url,
            )
        )

    job_status_str = job.status.value if hasattr(job.status, "value") else str(job.status)
    pending_count = max(0, job.total - job.succeeded - job.failed)

    return JobDetailResponse(
        job_id=job.id,
        event_name=job.event_name,
        status=job_status_str,
        total=job.total,
        succeeded=job.succeeded,
        failed=job.failed,
        pending=pending_count,
        created_at=job.created_at,
        completed_at=job.completed_at,
        certificates=cert_items,
    )
