
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.database import engine
from backend.app.models.job import Job
from backend.app.models.search import SearchTaskJob
from backend.app.repositories.search_repository import SearchRepository
from backend.app.schemas.job import (
    JobListing,
    JobSearchRequest,
    JobSource,
)
from backend.app.services.job_pipeline import (
    ExtractionFailure,
    PipelineResult,
)


repository = SearchRepository()


@pytest.fixture
def db_session():
    # Roll back test data after every test.
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


def create_request():
    return JobSearchRequest(
        keyword="Python Developer",
        location="United States",
        date_posted="24h",
    )


def make_job():
    return JobListing(
        source=JobSource.LINKEDIN,
        source_job_id=str(uuid4().int),
        job_url=f"https://www.linkedin.com/jobs/view/{uuid4().int}/",
        title="Senior Python Developer",
        company="Example Company",
        description="Complete Python job description.",
        skills=["Python", "FastAPI"],
    )


def test_create_and_retrieve_search(db_session):
    task = repository.create(
        db_session,
        create_request(),
        JobSource.LINKEDIN,
    )

    assert task.search_id is not None
    assert task.status == "pending"
    assert task.source == "linkedin"

    stored = repository.get(db_session, task.search_id)

    assert stored is not None
    assert stored.search_id == task.search_id
    assert stored.request_payload["keyword"] == "Python Developer"
    assert stored.request_payload["date_posted"] == "24h"


def test_complete_search_and_retrieve_results(db_session):
    task = repository.create(
        db_session,
        create_request(),
        JobSource.LINKEDIN,
    )

    repository.start(db_session, task.search_id)

    job = make_job()

    result = PipelineResult(
        source=JobSource.LINKEDIN,
        discovered_urls=[job.job_url],
        jobs=[job],
    )

    repository.complete(db_session, task.search_id, result)

    # A new session can read the persisted records.
    with Session(
        bind=db_session.connection(),
        join_transaction_mode="create_savepoint",
    ) as second_session:
        saved = repository.get_results(
            second_session,
            task.search_id,
        )

    assert saved is not None
    assert saved.status == "completed"
    assert saved.total_discovered == 1
    assert saved.total_extracted == 1
    assert saved.total_failed == 0

    assert len(saved.jobs) == 1
    assert saved.jobs[0].title == "Senior Python Developer"
    assert saved.jobs[0].description == "Complete Python job description."
    assert saved.jobs[0].skills == ["Python", "FastAPI"]


def test_partial_failure_is_persisted(db_session):
    task = repository.create(
        db_session,
        create_request(),
        JobSource.LINKEDIN,
    )

    repository.start(db_session, task.search_id)

    job = make_job()
    failed_url = "https://www.linkedin.com/jobs/view/999999/"

    result = PipelineResult(
        source=JobSource.LINKEDIN,
        discovered_urls=[job.job_url, failed_url],
        jobs=[job],
        failures=[
            ExtractionFailure(
                job_url=failed_url,
                error="Job description unavailable",
            )
        ],
    )

    repository.complete(db_session, task.search_id, result)

    saved = repository.get_results(db_session, task.search_id)

    assert saved.status == "completed"
    assert saved.total_discovered == 2
    assert saved.total_extracted == 1
    assert saved.total_failed == 1

    assert len(saved.jobs) == 1
    assert len(saved.failures) == 1
    assert saved.failures[0].job_url == failed_url


def test_failed_search_status(db_session):
    task = repository.create(db_session, create_request())

    repository.start(db_session, task.search_id)

    repository.fail(
        db_session,
        task.search_id,
        "Browser execution failed",
    )

    stored = repository.get(db_session, task.search_id)

    assert stored.status == "failed"
    assert stored.error == "Browser execution failed"
    assert stored.finished_at is not None

    with pytest.raises(ValueError):
        repository.start(db_session, task.search_id)


def test_date_exclusions_keep_persisted_totals_and_failures_distinct(db_session):
    from datetime import datetime, timezone
    from backend.app.services.job_pipeline import JobExtractionPipeline

    task = repository.create(db_session, create_request(), JobSource.LINKEDIN)
    repository.start(db_session, task.search_id)
    ids = [uuid4().int for _ in range(3)]
    urls = [f"https://www.linkedin.com/jobs/view/{job_id}/" for job_id in ids]
    pipeline = JobExtractionPipeline()
    result = pipeline.run(
        source=JobSource.LINKEDIN, search=create_request(),
        listing_html="".join(f'<a href="{url}">Job</a>' for url in urls),
        detail_pages={
            urls[0]: '<script type="application/ld+json">{"@type":"JobPosting","title":"Dev","hiringOrganization":{"name":"Acme"},"datePosted":"2026-10-08T10:00:00Z"}</script>',
            urls[1]: '<script type="application/ld+json">{"@type":"JobPosting","title":"Dev","hiringOrganization":{"name":"Acme"}}</script>',
        },
        now=datetime(2026, 10, 8, 12, tzinfo=timezone.utc),
    )
    repository.complete(db_session, task.search_id, result)
    saved = repository.get_results(db_session, task.search_id)
    assert saved.total_discovered == 3
    assert saved.total_extracted == 1
    assert saved.total_failed == 1
    assert [failure.job_url for failure in saved.failures] == [urls[2]]
    assert [job.job_url for job in saved.jobs] == [urls[0]]
    # Existing schema persists counts, jobs and failures, not excluded URL rows.
    assert set(saved.discovered_urls) == {urls[0], urls[2]}
