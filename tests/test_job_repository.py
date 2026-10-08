
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.database import engine
from backend.app.models.job import Job
from backend.app.repositories.job_repository import (
    JobRepository,
)
from backend.app.schemas.job import (
    Compensation,
    JobListing,
    JobSource,
    JobStatus,
)


repository = JobRepository()


@pytest.fixture
def db_session():
    """Isolated database transaction for each test."""

    with engine.connect() as connection:
        transaction = connection.begin()

        try:
            with Session(
                bind=connection,
                join_transaction_mode="create_savepoint",
            ) as session:
                yield session
        finally:
            transaction.rollback()


def make_job_url():
    return (
        f"https://www.linkedin.com/jobs/view/"
        f"{uuid4().int}/"
    )


def test_insert_job(db_session):
    listing = JobListing(
        source=JobSource.LINKEDIN,
        source_job_id="123456",
        job_url=make_job_url(),
        title="Senior Python Developer",
        company="Example Technology",
        location="New York",
        description="Build scalable Python APIs.",
        skills=["Python", "FastAPI"],
        posted_date=date(2026, 10, 8),
    )

    saved = repository.upsert(db_session, listing)

    assert saved.id is not None
    assert saved.title == "Senior Python Developer"
    assert saved.source == "linkedin"
    assert saved.description == "Build scalable Python APIs."
    assert saved.skills == ["Python", "FastAPI"]

    fetched = repository.get_by_id(
        db_session,
        saved.id,
    )

    assert fetched is not None
    assert fetched.id == saved.id


def test_upsert_prevents_duplicates(db_session):
    job_url = make_job_url()

    first = JobListing(
        source=JobSource.LINKEDIN,
        job_url=job_url,
        title="Python Developer",
        company="Example Company",
        description="Original description",
    )

    saved_first = repository.upsert(db_session, first)

    second = JobListing(
        source=JobSource.LINKEDIN,
        job_url=job_url,
        title="Senior Python Developer",
        company="Example Company",
        description="Updated description",
        skills=["Python", "PostgreSQL"],
    )

    saved_second = repository.upsert(db_session, second)

    assert saved_first.id == saved_second.id
    assert saved_second.title == "Senior Python Developer"
    assert saved_second.description == "Updated description"
    assert saved_second.skills == ["Python", "PostgreSQL"]

    count = db_session.scalar(
        select(func.count())
        .select_from(Job)
        .where(Job.job_url == job_url)
    )

    assert count == 1


def test_upsert_preserves_existing_data(db_session):
    job_url = make_job_url()

    first = JobListing(
        source=JobSource.LINKEDIN,
        job_url=job_url,
        title="Backend Engineer",
        company="Example Startup",
        description="Complete job description",
        skills=["Python", "Docker"],
        status=JobStatus.ACTIVE,
        compensation=Compensation(
            currency="USD",
            min_amount=120000,
            max_amount=160000,
            period="year",
        ),
    )

    initial = repository.upsert(db_session, first)
    original_job_id = initial.id

    assert initial.compensation is not None
    assert initial.compensation["currency"] == "USD"
    assert initial.compensation["min_amount"] == 120000
    assert initial.compensation["max_amount"] == 160000

    # Simulate a later extraction with missing fields.
    second = JobListing(
        source=JobSource.LINKEDIN,
        job_url=job_url,
        title="Backend Engineer",
        company="Example Startup",
    )

    updated = repository.upsert(db_session, second)

    assert updated.id == original_job_id
    assert updated.description == "Complete job description"
    assert updated.skills == ["Python", "Docker"]
    assert updated.status == "active"
    assert updated.compensation is not None
    assert updated.compensation["currency"] == "USD"
    assert updated.compensation["min_amount"] == 120000
    assert updated.compensation["max_amount"] == 160000

    third = JobListing(
        source=JobSource.LINKEDIN,
        job_url=job_url,
        title="Backend Engineer",
        company="Example Startup",
        compensation=Compensation(
            currency="USD",
            min_amount=140000,
            max_amount=180000,
            period="year",
        ),
    )

    replaced = repository.upsert(db_session, third)

    assert replaced.id == original_job_id
    assert replaced.compensation is not None
    assert replaced.compensation["currency"] == "USD"
    assert replaced.compensation["min_amount"] == 140000
    assert replaced.compensation["max_amount"] == 180000


@pytest.mark.parametrize("source", [JobSource.LINKEDIN, JobSource.WELLFOUND])
def test_upsert_normalizes_tracking_variations(db_session, source):
    job_id = uuid4().int
    canonical = (
        f"https://www.linkedin.com/jobs/view/{job_id}/"
        if source == JobSource.LINKEDIN
        else f"https://wellfound.com/jobs/{job_id}-python-developer"
    )
    first = JobListing(
        source=source, job_url=canonical + "?utm_source=first&trk=public_jobs#details",
        title="Developer", company="Acme", description="Full description",
    )
    saved_first = repository.upsert(db_session, first)
    first_id = saved_first.id
    second = first.model_copy(update={"job_url": canonical + "?utm_source=second", "title": "Senior Developer"})
    saved_second = repository.upsert(db_session, second)
    assert saved_second.id == first_id
    assert saved_second.job_url == canonical
    assert saved_second.title == "Senior Developer"
    assert saved_second.description == "Full description"
    assert "utm_source" in first.job_url  # Do not mutate callers' model instances.
    assert db_session.scalar(select(func.count()).select_from(Job).where(Job.job_url == canonical)) == 1
