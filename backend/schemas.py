from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, EmailStr, Field


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
    url: str | None = None


class ApplicationUpdate(BaseModel):
    company: str | None = None
    role: str | None = None
    date_applied: date | None = None
    status: StatusEnum | None = None
    notes: str | None = None
    url: str | None = None


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
