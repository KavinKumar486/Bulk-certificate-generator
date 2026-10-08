from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import verify_api_key
from app.db import get_db
from app.models import Certificate, CertificateStatus, Job
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


