from datetime import datetime, timezone
import logging
from typing import Any
from email_validator import EmailNotValidError, validate_email
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import Certificate, CertificateStatus, Job, JobStatus
from app.schemas import JobCreateRequest
from app.services import pdf_service

logger = logging.getLogger(__name__)


def create_job(db: Session, request: JobCreateRequest) -> Job:
    """
    Creates a new Job and its pending Certificate records atomically in one transaction.
    """
    job = Job(
        event_name=request.event_name,
        status=JobStatus.PENDING,
        total=len(request.recipients),
        succeeded=0,
        failed=0,
    )
    db.add(job)
    db.flush()

    for r in request.recipients:
        cert = Certificate(
            job_id=job.id,
            recipient_name=r.name or "",
            email=r.email,
            course=r.course,
            issue_date=r.date,
            status=CertificateStatus.PENDING,
        )
        db.add(cert)

    db.commit()
    db.refresh(job)
    return job


def validate_recipient(cert: Any) -> None:
    """
    Level 2 validation: validates recipient values.
    Raises ValueError with a human-readable message on failure.
    """
    # 1. Recipient name: required, non-blank after trim, max 100 chars
    raw_name = getattr(cert, "recipient_name", None)
    if raw_name is None:
        raw_name = getattr(cert, "name", "")
    name = str(raw_name).strip()
    if not name:
        raise ValueError("Recipient name is required and must not be blank")
    if len(name) > 100:
        raise ValueError("Recipient name must not exceed 100 characters")

    # 2. Email: optional; valid email format if provided
    email = getattr(cert, "email", None)
    if email is not None:
        email_str = str(email).strip()
        if email_str:
            try:
                validate_email(email_str, check_deliverability=False)
            except EmailNotValidError as e:
                raise ValueError(f"Invalid email format: {e}")

    # 3. Course: optional; max 150 chars
    course = getattr(cert, "course", None)
    if course is not None:
        course_str = str(course).strip()
        if len(course_str) > 150:
            raise ValueError("Course must not exceed 150 characters")

    # 4. Date: optional; must parse as ISO YYYY-MM-DD if provided
    raw_date = getattr(cert, "issue_date", None)
    if raw_date is None:
        raw_date = getattr(cert, "date", None)
    if raw_date is not None:
        date_str = str(raw_date).strip()
        if date_str:
            if len(date_str) != 10 or date_str.count("-") != 2:
                raise ValueError("Date must be in ISO format YYYY-MM-DD")
            try:
                datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                raise ValueError("Date must be in ISO format YYYY-MM-DD")


def process_job(job_id: str) -> None:
    """
    Background job processing algorithm per spec section 9:
    - Opens its OWN DB session (never reuses the request session).
    - job.status = processing; commit.
    - Iterates over pending certificates ordered by created_at.
    - Commits after EACH certificate.
    - Derives final job status and sets completed_at.
    - Wrapped in try/finally so the job is never left stuck in processing.
    - Re-runnable: only processes certificates with status == pending.
    """
    # Open dedicated DB session
    from app.db import SessionLocal as DBSessionLocal
    db = DBSessionLocal()
    try:
        job = db.query(Job).filter_by(id=job_id).first()
        if not job:
            logger.error("Job %s not found for processing", job_id)
            return

        job.status = JobStatus.PROCESSING
        db.commit()

        pending_certs = (
            db.query(Certificate)
            .filter_by(job_id=job.id, status=CertificateStatus.PENDING)
            .order_by(Certificate.created_at.asc())
            .all()
        )

        for cert in pending_certs:
            cert.status = CertificateStatus.PROCESSING
            db.commit()

            try:
                validate_recipient(cert)
                out_path = settings.STORAGE_DIR / job.id / f"{cert.id}.pdf"
                pdf_service.render_certificate(cert, job.event_name, out_path)
                cert.status = CertificateStatus.SUCCESS
                cert.file_path = str(out_path)
                cert.error_message = None
                job.succeeded += 1
            except Exception as exc:
                cert.status = CertificateStatus.FAILED
                cert.error_message = str(exc)
                job.failed += 1
                logger.exception("Error processing certificate %s for job %s", cert.id, job_id)
            finally:
                db.commit()

        # Update and derive final job status
        succeeded_count = (
            db.query(Certificate)
            .filter_by(job_id=job.id, status=CertificateStatus.SUCCESS)
            .count()
        )
        failed_count = (
            db.query(Certificate)
            .filter_by(job_id=job.id, status=CertificateStatus.FAILED)
            .count()
        )
        job.succeeded = succeeded_count
        job.failed = failed_count

        if job.succeeded == job.total:
            job.status = JobStatus.COMPLETED
        elif job.failed == job.total:
            job.status = JobStatus.FAILED
        else:
            job.status = JobStatus.COMPLETED_WITH_ERRORS

        job.completed_at = datetime.now(timezone.utc)
        db.commit()

    except Exception:
        logger.exception("Unexpected error in process_job for job %s", job_id)
        try:
            job = db.query(Job).filter_by(id=job_id).first()
            if job and job.status == JobStatus.PROCESSING:
                succeeded_count = (
                    db.query(Certificate)
                    .filter_by(job_id=job.id, status=CertificateStatus.SUCCESS)
                    .count()
                )
                failed_count = (
                    db.query(Certificate)
                    .filter_by(job_id=job.id, status=CertificateStatus.FAILED)
                    .count()
                )
                job.succeeded = succeeded_count
                job.failed = failed_count
                if job.succeeded > 0 and job.failed > 0:
                    job.status = JobStatus.COMPLETED_WITH_ERRORS
                elif job.succeeded > 0 and job.failed == 0:
                    job.status = JobStatus.COMPLETED
                else:
                    job.status = JobStatus.FAILED
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            logger.exception("Failed to recover final status for job %s", job_id)
    finally:
        db.close()
