
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

class JobSearchRequest(BaseModel):
    """Offline extraction input, retained for reusable parser tests; never an API request."""
    source: Literal["linkedin", "wellfound", "careerhub", "greenhouse"] = "linkedin"
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
        if not self.keyword:
            raise ValueError("Keyword cannot be empty")
        return self


# ==========================================
# JOB DETAILS ENUMS
# ==========================================

class JobSource(str, Enum):
    LINKEDIN = "linkedin"
    WELLFOUND = "wellfound"
    CAREERHUB = "careerhub"
    GREENHOUSE = "greenhouse"
    ASHBY = "ashby"
    LEVER = "lever"
    REMOTIVE = "remotive"
    USAJOBS = "usajobs"
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
