from datetime import date, datetime
from enum import Enum
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, HttpUrl


def validate_posting_url(value: str) -> str:
    value = value.strip()
    if value:
        if not value.lower().startswith(("http://", "https://")):
            raise ValueError("Job posting URL must be an absolute HTTP or HTTPS URL")
        HttpUrl(value)
    return value


PostingURL = Annotated[str, AfterValidator(validate_posting_url)]


class StatusEnum(str, Enum):
    applied = "Applied"
    interview = "Interview"
    offer = "Offer"
    rejected = "Rejected"
    withdrawn = "Withdrawn"


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ApplicationCreate(BaseModel):
    company: str
    role: str
    date_applied: date
    status: StatusEnum = StatusEnum.applied
    notes: str | None = None
    url: PostingURL | None = None


class ApplicationUpdate(BaseModel):
    company: str | None = None
    role: str | None = None
    date_applied: date | None = None
    status: StatusEnum | None = None
    notes: str | None = None
    url: PostingURL | None = None


class ApplicationResponse(BaseModel):
    id: int
    company: str
    role: str
    status: StatusEnum
    date_applied: date
    notes: str | None
    url: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StatsResponse(BaseModel):
    total: int
    by_status: dict[str, int]
