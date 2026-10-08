
from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class Job(Base):
    __tablename__ = "jobs"

    __table_args__ = (
        UniqueConstraint(
            "source",
            "job_url",
            name="uq_jobs_source_url",
        ),
        Index(
            "ix_jobs_source_posted_date",
            "source",
            "posted_date",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # Source identification
    source: Mapped[str] = mapped_column(String(32))
    source_job_id: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    job_url: Mapped[str] = mapped_column(String(2048))
    application_url: Mapped[str | None] = mapped_column(
        String(2048), nullable=True
    )

    # Basic details
    title: Mapped[str] = mapped_column(String(500))
    company: Mapped[str] = mapped_column(String(500))
    company_url: Mapped[str | None] = mapped_column(
        String(2048), nullable=True
    )
    location: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )

    # Employment
    workplace_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    employment_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    seniority_level: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )

    # Complete job description
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    responsibilities: Mapped[list] = mapped_column(
        JSONB, default=list
    )
    requirements: Mapped[list] = mapped_column(
        JSONB, default=list
    )
    skills: Mapped[list] = mapped_column(
        JSONB, default=list
    )

    # Experience
    experience_min_years: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    experience_max_years: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )

    # Compensation
    compensation: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )

    # Posting information
    posted_date: Mapped[date | None] = mapped_column(
        Date, nullable=True
    )
    posted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    posted_text: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )

    # Job status
    status: Mapped[str] = mapped_column(
        String(32),
        default="unknown",
        server_default="unknown",
    )

    # Tracking
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
