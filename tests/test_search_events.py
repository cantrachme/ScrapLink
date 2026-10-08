from concurrent.futures import ThreadPoolExecutor
from time import monotonic, sleep
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text

from backend.app.database import SessionLocal
from backend.app.main import app
from backend.app.models.search import SearchTaskRecord
from backend.app.models.search_event import SearchEvent
from backend.app.repositories.search_event_repository import SearchEventRepository as Events
from backend.app.repositories.search_repository import SearchRepository as Searches
from backend.app.schemas.job import JobSearchRequest, JobSource


@pytest.fixture
def searches():
    ids = []

    def create():
        with SessionLocal.begin() as db:
            task = Searches.create(db, JobSearchRequest(keyword="Python"), JobSource.LINKEDIN)
            ids.append(task.search_id)
            return task.search_id

    yield create
    with SessionLocal.begin() as db:
        db.execute(delete(SearchTaskRecord).where(SearchTaskRecord.search_id.in_(ids)))


def queued(db, search_id):
    return Events.publish(db, search_id, "search_queued", {
        "search_id": str(search_id), "status": "pending", "source": "linkedin",
    })


def page(db, search_id, number=1):
    return Events.publish(db, search_id, "page_discovered", {
        "page_number": number, "new_jobs_discovered": 1, "total_discovered": number,
    })


def test_publish_order_isolation_and_committed_session_visibility(searches):
    first, second = searches(), searches()
    with SessionLocal.begin() as db:
        event = queued(db, first)
        page(db, first)
        queued(db, second)
        assert event.sequence == 1
        assert event.created_at.tzinfo is not None
        with SessionLocal() as reader:
            assert Events.get_after(reader, first, 0) == []
    with SessionLocal() as reader:
        events = Events.get_after(reader, first, 0)
        assert [event.sequence for event in events] == [1, 2]
        assert all(event.search_id == first for event in events)
        assert [event.sequence for event in Events.get_after(reader, first, 1)] == [2]
        assert len(Events.get_after(reader, first, 0, limit=1)) == 1
        assert Events.get_after(reader, first, 2) == []
        assert Events.get_after(reader, second, 0)[0].sequence == 1
    # DTO fields remain accessible and do not depend on an open ORM session.
    assert events[0].payload["source"] == "linkedin"


def test_rollback_removes_event_and_does_not_consume_sequence(searches):
    search_id = searches()
    with SessionLocal() as db:
        queued(db, search_id)
        db.rollback()
    with SessionLocal.begin() as db:
        assert Events.get_after(db, search_id, 0) == []
        assert queued(db, search_id).sequence == 1


def test_missing_search_has_clear_error():
    with SessionLocal.begin() as db:
        with pytest.raises(KeyError, match="Search task not found"):
            queued(db, uuid4())
        with pytest.raises(KeyError, match="Search task not found"):
            Events.get_after(db, uuid4(), 0)


def test_parent_deletion_cascades(searches):
    search_id = searches()
    with SessionLocal.begin() as db:
        queued(db, search_id)
    with SessionLocal.begin() as db:
        db.execute(delete(SearchTaskRecord).where(SearchTaskRecord.search_id == search_id))
    with SessionLocal() as db:
        assert db.scalar(select(SearchEvent).where(SearchEvent.search_id == search_id)) is None


def test_concurrent_publishers_wait_for_parent_lock(searches):
    search_id = searches()
    application_name = f"sse-test-{uuid4()}"

    def second_publisher():
        with SessionLocal.begin() as db:
            db.execute(text("SET LOCAL statement_timeout = '5s'"))
            db.execute(text("SELECT set_config('application_name', :name, true)"), {"name": application_name})
            return page(db, search_id, 2)

    with ThreadPoolExecutor(max_workers=1) as pool:
        with SessionLocal.begin() as first:
            assert page(first, search_id).sequence == 1
            future = pool.submit(second_publisher)
            # Observe an actual PostgreSQL lock wait, rather than assuming a
            # sleep means both publishers overlapped. Every wait is bounded.
            deadline = monotonic() + 3
            while True:
                with SessionLocal() as observer:
                    waiting = observer.scalar(text(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE application_name = :name AND wait_event_type = 'Lock'"
                    ), {"name": application_name})
                if waiting:
                    break
                assert monotonic() < deadline, "Second publisher never waited for the parent lock"
                sleep(0.01)
            assert not future.done()
        assert future.result(timeout=5).sequence == 2
    with SessionLocal() as db:
        events = Events.get_after(db, search_id, 0)
        assert [event.sequence for event in events] == [1, 2]
        assert [event.payload["page_number"] for event in events] == [1, 2]


@pytest.mark.parametrize("event_type,payload", [
    ("unknown", {}),
    ("page_discovered", {"page_number": 1, "new_jobs_discovered": 1, "total_discovered": 1, "cookies": "secret"}),
    ("page_discovered", {"page_number": 1, "new_jobs_discovered": 1, "total_discovered": float("nan")}),
    ("job_failed", {"job_url": "https://example.com/job", "error": "<html>secret</html>", "total_failed": 1}),
    ("job_extracted", {"job_url": "https://user:password@example.com/job", "title": "Dev", "company": "Acme", "total_extracted": 1}),
    ("job_extracted", {"job_url": "https://example.com/job", "title": "<html>raw</html>", "company": "Acme", "total_extracted": 1}),
    ("page_discovered", {"page_number": 1, "new_jobs_discovered": 1, "total_discovered": object()}),
])
def test_reject_invalid_or_unsafe_payloads(searches, event_type, payload):
    with SessionLocal.begin() as db:
        search_id = searches()
        with pytest.raises(ValueError):
            Events.publish(db, search_id, event_type, payload)
        assert Events.get_after(db, search_id, 0) == []


def test_event_url_drops_query_and_fragment(searches):
    with SessionLocal.begin() as db:
        event = Events.publish(db, searches(), "job_extracted", {
            "job_url": "https://example.com/job?session=secret#token",
            "title": "Python Engineer", "company": "Acme", "total_extracted": 1,
        })
        assert event.payload["job_url"] == "https://example.com/job"


def test_search_id_must_match_parent(searches):
    with SessionLocal.begin() as db, pytest.raises(ValueError, match="parent search"):
        Events.publish(db, searches(), "search_queued", {
            "search_id": str(uuid4()), "source": "linkedin", "status": "pending",
        })


@pytest.mark.parametrize("cursor,limit", [(-1, 100), (True, 100), (0, 0), (0, 1001)])
def test_invalid_repository_cursor_or_limit(searches, cursor, limit):
    with SessionLocal() as db, pytest.raises(ValueError):
        Events.get_after(db, searches(), cursor, limit)


def test_api_queue_event_commits_with_search():
    response = TestClient(app).post("/api/v1/jobs/search", json={"keyword": "Python"})
    assert response.status_code == 202
    search_id = response.json()["search_id"]
    try:
        with SessionLocal() as db:
            events = Events.get_after(db, search_id, 0)
            assert [e.event_type for e in events] == ["search_queued"]
            assert events[0].payload == {"search_id": search_id, "status": "pending", "source": "linkedin"}
            assert Searches.get(db, search_id).status == "pending"
    finally:
        with SessionLocal.begin() as db:
            db.execute(delete(SearchTaskRecord).where(SearchTaskRecord.search_id == search_id))


def test_api_queued_event_failure_rolls_back_search(monkeypatch):
    ids = []
    original = Events.publish

    def fail_after_insert(db, search_id, event_type, payload):
        ids.append(search_id)
        original(db, search_id, event_type, payload)
        raise RuntimeError("Simulated event persistence error")

    monkeypatch.setattr(Events, "publish", fail_after_insert)
    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/jobs/search", json={"keyword": "Python"},
    )
    assert response.status_code == 500
    assert len(ids) == 1
    with SessionLocal() as db:
        assert Searches.get(db, ids[0]) is None
        assert db.scalar(select(SearchEvent).where(SearchEvent.search_id == ids[0])) is None
