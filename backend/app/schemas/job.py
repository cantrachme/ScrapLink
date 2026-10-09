
from datetime import date, datetime, timezone
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


# ==========================================
# JOB SEARCH MODELS
# ==========================================

class DatePosted(str, Enum):
    PAST_24_HOURS = "24h"
    PAST_WEEK = "7d"
    PAST_MONTH = "30d"


class ActiveJobsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_results: int = Field(default=50, ge=1, le=500)
    watch_mode: bool = True
    watch_delay_seconds: float = Field(default=2.0, ge=1.5, le=3.0)


class JobSearchRequest(BaseModel):
    mode: Literal["search", "active_jobs"] = "search"
    source: Literal["linkedin", "wellfound", "careerhub"] = "linkedin"
    keyword: str = Field(
        default="",
        max_length=200,
        description="Job title or search keywords",
    )

    location: str = Field(
        default="United States",
        max_length=200,
    )

    date_posted: Literal["any", "24h", "7d", "30d"] = "24h"
    watch_mode: bool = True
    watch_delay_seconds: float = Field(default=2.0, ge=1.5, le=3.0)

    max_results: int = Field(
        default=50,
        ge=1,
        le=500,
    )

    @field_validator("keyword", "location")
    @classmethod
    def strip_whitespace(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_discovery(self):
        if self.mode == "search" and not self.keyword:
            raise ValueError("Keyword cannot be empty")
        if self.mode == "active_jobs" and (self.keyword or self.location or self.date_posted != "24h"
                                           or self.source not in ("linkedin", "wellfound")):
            raise ValueError("Active Jobs requires unrestricted LinkedIn/Wellfound discovery in the last 24 hours")
        return self


class JobSearchResponse(BaseModel):
    search_id: str
    status: str
    message: str


# ==========================================
# JOB DETAILS ENUMS
# ==========================================

class JobSource(str, Enum):
    LINKEDIN = "linkedin"
    WELLFOUND = "wellfound"
    CAREERHUB = "careerhub"
    REALPYTHON_DEMO = "realpython_demo"


class JobStatus(str, Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class WorkplaceType(str, Enum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"


class EmploymentType(str, Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    TEMPORARY = "temporary"
    OTHER = "other"


# ==========================================
# COMPENSATION MODEL
# ==========================================

class Compensation(BaseModel):
    raw_text: str | None = None
    currency: str | None = None

    min_amount: float | None = Field(
        default=None,
        ge=0,
    )

    max_amount: float | None = Field(
        default=None,
        ge=0,
    )

    period: Literal["hour", "month", "year"] | None = None

    @model_validator(mode="after")
    def validate_range(self):
        if (
            self.min_amount is not None
            and self.max_amount is not None
            and self.min_amount > self.max_amount
        ):
            raise ValueError(
                "Minimum compensation cannot exceed maximum"
            )
        return self


# ==========================================
# JOB DETAILS MODEL
# ==========================================

class JobListing(BaseModel):

    # Source identification
    source: JobSource
    source_job_id: str | None = None

    job_url: str = Field(min_length=1)
    application_url: str | None = None

    # Basic job details
    title: str = Field(min_length=1)
    # Empty is the compatible representation for an unavailable company.
    company: str = Field(default="", max_length=500)

    company_url: str | None = None
    location: str | None = None

    # Employment details
    workplace_type: WorkplaceType | None = None
    employment_type: EmploymentType | None = None
    seniority_level: str | None = None

    # Complete job description
    description: str | None = None

    responsibilities: list[str] = Field(
        default_factory=list
    )

    requirements: list[str] = Field(
        default_factory=list
    )

    skills: list[str] = Field(
        default_factory=list
    )

    # Experience
    experience_min_years: float | None = Field(
        default=None,
        ge=0,
    )

    experience_max_years: float | None = Field(
        default=None,
        ge=0,
    )

    # Compensation
    compensation: Compensation | None = None

    # Posting information
    posted_date: date | None = None
    posted_at: datetime | None = None
    posted_text: str | None = None

    # Verification
    status: JobStatus = JobStatus.UNKNOWN

    # Tracking
    first_seen_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    last_verified_at: datetime | None = None


class PersistedJobResponse(JobListing):
    """Read-only stored job; collectors continue to supply JobListing without IDs."""

    id: UUID
    updated_at: datetime


class JobExtractionFailure(BaseModel):
    source: JobSource | None = None
    job_url: str
    error: str


class JobSearchResultsResponse(BaseModel):
    source_statuses: dict[str, str] = Field(default_factory=dict)
    search_id: str
    status: str
    source: JobSource | None = None

    discovered_urls: list[str] = Field(
        default_factory=list
    )
    jobs: list[PersistedJobResponse] = Field(
        default_factory=list
    )
    failures: list[JobExtractionFailure] = Field(
        default_factory=list
    )

    total_discovered: int = 0
    total_extracted: int = 0
    total_failed: int = 0


class AssistedJobInput(BaseModel):
    source: Literal["linkedin", "wellfound"] | None = None
    company: str = Field(default="", max_length=500)
    compensation: Compensation | None = None
    posted_date: date | None = None
    posted_at: datetime | None = None
    posted_text: str | None = Field(default=None, max_length=255)
    title: str = Field(min_length=1, max_length=500)
    job_url: str = Field(max_length=2048)
    location: str | None = Field(default=None, max_length=500)
    workplace_type: WorkplaceType | None = None
    description: str | None = Field(default=None, max_length=100000)

    @field_validator("title", "job_url")
    @classmethod
    def nonempty(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Cannot be empty")
        return value
