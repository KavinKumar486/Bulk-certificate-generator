from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from app.auth import verify_api_key
from app.db import get_db
from app.schemas import JobCreateRequest, JobCreateResponse
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
