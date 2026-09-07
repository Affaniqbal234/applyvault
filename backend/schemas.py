from datetime import date, datetime
from enum import Enum
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    Field,
    HttpUrl,
    StringConstraints,
    field_validator,
)


def normalize_optional_text(value):
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def validate_posting_url(value: str | None) -> str | None:
    if value is None:
        return None
    if len(value) > 2048:
        raise ValueError("Job posting URL cannot exceed 2048 characters")
    if not value.lower().startswith(("http://", "https://")):
        raise ValueError("Job posting URL must be an absolute HTTP or HTTPS URL")
    HttpUrl(value)
    return value


def validate_application_date(value: date) -> date:
    if value > date.today():
        raise ValueError("Application date cannot be in the future")
    return value


RequiredApplicationText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]
OptionalNotes = Annotated[str | None, BeforeValidator(normalize_optional_text)]
PostingURL = Annotated[
    str | None,
    BeforeValidator(normalize_optional_text),
    AfterValidator(validate_posting_url),
]
ApplicationDate = Annotated[date, AfterValidator(validate_application_date)]


class StatusEnum(str, Enum):
    applied = "Applied"
    interview = "Interview"
    offer = "Offer"
    rejected = "Rejected"
    withdrawn = "Withdrawn"


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password cannot exceed 72 UTF-8 bytes")
        return value


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CurrentUserResponse(BaseModel):
    email: EmailStr


class ApplicationCreate(BaseModel):
    company: RequiredApplicationText
    role: RequiredApplicationText
    date_applied: ApplicationDate
    status: StatusEnum = StatusEnum.applied
    notes: OptionalNotes = None
    url: PostingURL = None


class ApplicationUpdate(BaseModel):
    company: RequiredApplicationText | None = None
    role: RequiredApplicationText | None = None
    date_applied: ApplicationDate | None = None
    status: StatusEnum | None = None
    notes: OptionalNotes = None
    url: PostingURL = None

    @field_validator("company", "role", "date_applied", "status")
    @classmethod
    def required_fields_cannot_be_cleared(cls, value):
        if value is None:
            raise ValueError("Required application fields cannot be null")
        return value


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
