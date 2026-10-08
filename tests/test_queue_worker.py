
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select

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
from backend.app.repositories.search_event_repository import SearchEventRepository as Events
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
        with SessionLocal() as db:
            assert repository.get(db, search_id).status == "running"
            assert [e.event_type for e in Events.get_after(db, search_id, 0)] == ["search_started"]

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
        events = Events.get_after(db, search_id, 0)
        assert [e.event_type for e in events] == ["search_started", "search_completed"]
        assert events[-1].payload == {
            "search_id": str(search_id), "status": "completed",
            "total_discovered": 1, "total_extracted": 1, "total_failed": 0,
        }


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
        events = Events.get_after(db, search_id, 0)
        assert [e.event_type for e in events] == ["search_started", "search_failed"]
        assert events[-1].payload["error"] == "Search execution failed"


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


def test_worker_progress_is_committed_before_collection_continues(test_data):
    create_search, _ = test_data
    first, second = create_search(), create_search()
    calls = []

    class ProgressCollector:
        def __call__(self, source, request):
            pytest.fail("Must not also invoke the legacy collector interface")

        def collect_with_progress(self, source, request, progress):
            calls.append(source)
            progress("page_discovered", {
                "page_number": 1, "new_jobs_discovered": 0, "total_discovered": 0,
            })
            with SessionLocal.begin() as db:
                # A separate session can acquire the row immediately: no
                # transaction or parent lock survives across browser actions.
                db.execute(select(SearchTaskRecord).where(
                    SearchTaskRecord.search_id == first,
                ).with_for_update(nowait=True))
                assert [e.event_type for e in Events.get_after(db, first, 0)] == [
                    "search_started", "page_discovered",
                ]
                assert Events.get_after(db, second, 0) == []
            return PipelineResult(source=source)

    assert JobQueueWorker(ProgressCollector()).run_once(first)
    assert calls == [JobSource.LINKEDIN]
    with SessionLocal() as db:
        assert [e.event_type for e in Events.get_after(db, first, 0)] == [
            "search_started", "page_discovered", "search_completed",
        ]


def test_start_event_failure_rolls_back_claim(test_data, monkeypatch):
    create_search, _ = test_data
    search_id = create_search()
    worker = JobQueueWorker(lambda *args: pytest.fail("Collector must not run"))
    publish = worker.events.publish

    def failing_publish(db, search_id, event_type, payload):
        publish(db, search_id, event_type, payload)
        raise RuntimeError("Event storage failed")

    monkeypatch.setattr(worker.events, "publish", failing_publish)
    with pytest.raises(RuntimeError, match="Event storage failed"):
        worker.run_once(search_id)
    with SessionLocal() as db:
        assert repository.get(db, search_id).status == "pending"
        assert Events.get_after(db, search_id, 0) == []


def test_completion_event_failure_rolls_back_results(test_data, monkeypatch):
    from backend.app.services.job_pipeline import ExtractionFailure

    create_search, job_urls = test_data
    search_id = create_search()
    job_url = f"https://www.linkedin.com/jobs/view/{uuid4().int}/"
    job_urls.append(job_url)
    result = PipelineResult(
        source=JobSource.LINKEDIN, discovered_urls=[job_url, job_url + "missing"],
        jobs=[JobListing(source=JobSource.LINKEDIN, job_url=job_url, title="Dev", company="Acme")],
        failures=[ExtractionFailure(job_url=job_url + "missing", error="Unavailable")],
    )
    worker = JobQueueWorker(lambda source, request: result)
    publish = worker.events.publish

    def failing_publish(db, search_id, event_type, payload):
        event = publish(db, search_id, event_type, payload)
        if event_type == "search_completed":
            with SessionLocal() as reader:
                assert repository.get(reader, search_id).status == "running"
                assert repository.get_results(reader, search_id).jobs == []
                assert [e.event_type for e in Events.get_after(reader, search_id, 0)] == ["search_started"]
            raise RuntimeError("Completion event storage failed")
        return event

    monkeypatch.setattr(worker.events, "publish", failing_publish)
    assert worker.run_once(search_id)
    with SessionLocal() as db:
        saved = repository.get_results(db, search_id)
        assert saved.status == "failed"
        assert saved.jobs == saved.failures == []
        assert db.scalar(select(Job).where(Job.job_url == job_url)) is None
        assert [e.event_type for e in Events.get_after(db, search_id, 0)] == ["search_started", "search_failed"]


def test_failure_event_error_rolls_back_failed_status_and_propagates(test_data, monkeypatch):
    create_search, _ = test_data
    search_id = create_search()

    def collector(source, request):
        raise RuntimeError("Browser failed")

    worker = JobQueueWorker(collector)
    publish = worker.events.publish

    def failing_publish(db, search_id, event_type, payload):
        event = publish(db, search_id, event_type, payload)
        if event_type == "search_failed":
            raise RuntimeError("Failure event storage failed")
        return event

    monkeypatch.setattr(worker.events, "publish", failing_publish)
    with pytest.raises(RuntimeError, match="Failure event storage failed"):
        worker.run_once(search_id)
    with SessionLocal() as db:
        assert repository.get(db, search_id).status == "running"
        assert [e.event_type for e in Events.get_after(db, search_id, 0)] == ["search_started"]


def test_progress_persistence_failure_marks_search_failed(test_data, monkeypatch):
    create_search, _ = test_data
    search_id = create_search()

    class Collector:
        def collect_with_progress(self, source, request, progress):
            progress("page_discovered", {"page_number": 1, "new_jobs_discovered": 0, "total_discovered": 0})
            pytest.fail("Progress storage failure must abort collection")

    worker = JobQueueWorker(Collector())
    publish = worker.events.publish

    def failing_publish(db, search_id, event_type, payload):
        if event_type == "page_discovered":
            raise RuntimeError("Progress storage failed")
        return publish(db, search_id, event_type, payload)

    monkeypatch.setattr(worker.events, "publish", failing_publish)
    assert worker.run_once(search_id)
    with SessionLocal() as db:
        assert repository.get(db, search_id).status == "failed"
        assert [e.event_type for e in Events.get_after(db, search_id, 0)] == ["search_started", "search_failed"]
