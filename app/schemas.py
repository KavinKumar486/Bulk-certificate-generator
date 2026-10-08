from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, StrictStr, field_validator

from app.config import settings


class RecipientIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: Optional[StrictStr] = ""
    email: Optional[StrictStr] = None
    course: Optional[StrictStr] = None
    date: Optional[StrictStr] = None


class JobCreateRequest(BaseModel):
    event_name: StrictStr
    recipients: list[RecipientIn]

    @field_validator("event_name", mode="after")
    @classmethod
    def validate_event_name(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed or len(trimmed) > 200:
            raise ValueError("event_name must be between 1 and 200 characters after trimming")
        return trimmed

    @field_validator("recipients", mode="after")
    @classmethod
    def validate_recipients(cls, v: list[RecipientIn]) -> list[RecipientIn]:
        if not v:
            raise ValueError("recipients list must not be empty")
        if len(v) > settings.MAX_RECIPIENTS_PER_REQUEST:
            raise ValueError(f"recipients list must not exceed {settings.MAX_RECIPIENTS_PER_REQUEST} items")
        return v


class JobCreateResponse(BaseModel):
    job_id: str
    status: str
    total: int


class CertificateItemResponse(BaseModel):
    id: str
    recipient_name: str
    status: str
    error_message: Optional[str] = None
    download_url: Optional[str] = None


class JobDetailResponse(BaseModel):
    job_id: str
    event_name: str
    status: str
    total: int
    succeeded: int
    failed: int
    pending: int
    created_at: datetime
    completed_at: Optional[datetime] = None
    certificates: list[CertificateItemResponse]
