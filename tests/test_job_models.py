
import pytest
from pydantic import ValidationError

from backend.app.schemas.job import (
    JobListing,
    JobSource,
    JobStatus,
    WorkplaceType,
    EmploymentType,
    Compensation,
)


def test_linkedin_job():
    job = JobListing(
        source=JobSource.LINKEDIN,
        source_job_id="123456",
        job_url="https://www.linkedin.com/jobs/view/123456/",
        title="Senior Python Developer",
        company="Example Tech",
        location="New York, United States",
        workplace_type=WorkplaceType.REMOTE,
        employment_type=EmploymentType.FULL_TIME,
        description="Complete job description",
        skills=["Python", "FastAPI", "PostgreSQL"],
        experience_min_years=5,
        status=JobStatus.UNKNOWN,
    )

    assert job.source == JobSource.LINKEDIN
    assert job.description == "Complete job description"
    assert len(job.skills) == 3
    assert job.status == JobStatus.UNKNOWN


def test_wellfound_job():
    job = JobListing(
        source=JobSource.WELLFOUND,
        source_job_id="98765",
        job_url="https://wellfound.com/jobs/98765",
        title="AI Engineer",
        company="Example AI Startup",
        location="Remote",
        description="Complete AI engineering job description",
        compensation=Compensation(
            currency="USD",
            min_amount=120000,
            max_amount=180000,
            period="year",
        ),
    )

    assert job.source == JobSource.WELLFOUND
    assert job.compensation.currency == "USD"
    assert job.compensation.min_amount == 120000


def test_existing_demo_compatibility():
    job = JobListing(
        title="Python Developer",
        company="Demo Company",
        location="Remote",
        job_url="https://example.com/jobs/1",
        source="realpython_demo",
    )

    assert job.source == JobSource.REALPYTHON_DEMO
    assert job.description is None
    assert job.status == JobStatus.UNKNOWN


def test_invalid_compensation():
    with pytest.raises(ValidationError):
        Compensation(
            min_amount=200000,
            max_amount=100000,
        )


def test_json_serialization():
    job = JobListing(
        source=JobSource.LINKEDIN,
        title="Backend Engineer",
        company="Example Company",
        job_url="https://example.com/jobs/2",
    )

    data = job.model_dump(mode="json")

    assert data["source"] == "linkedin"
    assert data["status"] == "unknown"
    assert isinstance(data["skills"], list)
    assert data["first_seen_at"] is not None
