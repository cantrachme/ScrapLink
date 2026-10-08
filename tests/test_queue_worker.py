
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete

from backend.app.database import SessionLocal
from backend.app.models.job import Job
from backend.app.models.search import SearchTaskRecord
from backend.app.repositories.search_repository import (
    SearchRepository,
)
from backend.app.schemas.job import (
    JobListing,
    JobSearchRequest,
    JobSource,
)
from backend.app.services.job_pipeline import PipelineResult
from backend.app.workers.queue_worker import JobQueueWorker


repository = SearchRepository()


@pytest.fixture
def test_data():
    search_ids = []
    job_urls = []

    def create_search(source=JobSource.LINKEDIN):
        with SessionLocal.begin() as db:
            task = repository.create(
                db,
                JobSearchRequest(
                    keyword="Python Developer",
                    source=source.value,
                ),
                source=source,
            )
            search_id = task.search_id

        search_ids.append(search_id)
        return search_id

    yield create_search, job_urls

    with SessionLocal.begin() as db:
        if search_ids:
            db.execute(
                delete(SearchTaskRecord).where(
                    SearchTaskRecord.search_id.in_(
                        search_ids
                    )
                )
            )

        if job_urls:
            db.execute(
                delete(Job).where(
                    Job.job_url.in_(job_urls)
                )
            )


def test_claim_pending_search(test_data):
    create_search, _ = test_data
    search_id = create_search()

    with SessionLocal.begin() as db:
        task = repository.claim_next_pending(
            db,
            search_id,
        )

        assert task is not None
        assert task.status == "running"
        assert task.started_at is not None

    with SessionLocal() as db:
        saved = repository.get(db, search_id)
        assert saved.status == "running"


def test_worker_completes_search(test_data):
    create_search, job_urls = test_data
    search_id = create_search()

    job_id = uuid4().int
    job_url = (
        f"https://www.linkedin.com/jobs/view/"
        f"{job_id}/"
    )
    job_urls.append(job_url)

    def fake_collector(source, request):
        assert source == JobSource.LINKEDIN
        assert request.keyword == "Python Developer"

        job = JobListing(
            source=source,
            job_url=job_url,
            title="Python Developer",
            company="Example Company",
            description="Complete test job description.",
        )

        return PipelineResult(
            source=source,
            discovered_urls=[job_url],
            jobs=[job],
        )

    worker = JobQueueWorker(fake_collector)

    assert worker.run_once(search_id) is True

    with SessionLocal() as db:
        task = repository.get(db, search_id)
        results = repository.get_results(db, search_id)

        assert task.status == "completed"
        assert results.total_extracted == 1
        assert results.jobs[0].title == "Python Developer"


def test_worker_records_failure(test_data):
    create_search, _ = test_data
    search_id = create_search()

    def failing_collector(source, request):
        raise RuntimeError("Test browser failure")

    worker = JobQueueWorker(failing_collector)

    assert worker.run_once(search_id) is True

    with SessionLocal() as db:
        task = repository.get(db, search_id)

        assert task.status == "failed"
        assert "Test browser failure" in task.error
        assert task.finished_at is not None


def test_completed_task_cannot_be_claimed_again(test_data):
    create_search, _ = test_data
    search_id = create_search()

    calls = []

    def empty_collector(source, request):
        calls.append(source)
        return PipelineResult(source=source)

    worker = JobQueueWorker(empty_collector)

    assert worker.run_once(search_id) is True
    assert worker.run_once(search_id) is False
    assert len(calls) == 1


def test_missing_task_returns_false():
    worker = JobQueueWorker(
        lambda source, request: PipelineResult(
            source=source
        )
    )

    assert worker.run_once(uuid4()) is False
