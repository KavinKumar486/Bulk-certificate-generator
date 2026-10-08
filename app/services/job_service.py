from datetime import datetime
from typing import Any
from email_validator import EmailNotValidError, validate_email
from sqlalchemy.orm import Session

from app.models import Certificate, CertificateStatus, Job, JobStatus
from app.schemas import JobCreateRequest


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
    Background job processing placeholder for CP2.
    Full processing algorithm will be implemented in CP3.
    """
    pass
