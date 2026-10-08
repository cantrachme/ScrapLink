import asyncio
import json
from threading import get_ident
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from backend.app.api.routes import jobs as routes
from backend.app.config import settings
from backend.app.database import SessionLocal, engine
from backend.app.main import app
from backend.app.models.search import SearchTaskRecord
from backend.app.repositories.search_event_repository import SearchEventRepository as Events
from backend.app.repositories.search_repository import SearchRepository as Searches
from backend.app.schemas.job import JobSearchRequest, JobSource
from backend.app.services import search_event_stream as streaming
from backend.app.services.job_pipeline import PipelineResult
from backend.app.workers.queue_worker import JobQueueWorker


@pytest.fixture(autouse=True)
def bounded_http_stream(monkeypatch):
    original = routes.stream_search_events

    async def bounded(*args, **kwargs):
        # TestClient buffers streams. A regression must fail, never hang pytest.
        async with asyncio.timeout(3):
            async for chunk in original(*args, **kwargs):
                yield chunk

    monkeypatch.setattr(routes, "stream_search_events", bounded)


@pytest.fixture
def search_factory():
    ids = []

    def create(*, completed=True, pages=0):
        with SessionLocal.begin() as db:
            task = Searches.create(db, JobSearchRequest(keyword="Python"), JobSource.LINKEDIN)
            search_id = task.search_id
            ids.append(search_id)
            Events.publish(db, search_id, "search_queued", {
                "search_id": str(search_id), "status": "pending", "source": "linkedin",
            })
            if completed:
                Searches.start(db, search_id)
                Events.publish(db, search_id, "search_started", {
                    "search_id": str(search_id), "status": "running", "source": "linkedin",
                })
            for page_number in range(1, pages + 1):
                Events.publish(db, search_id, "page_discovered", {
                    "page_number": page_number, "new_jobs_discovered": 0, "total_discovered": 0,
                })
            if completed:
                Searches.complete(db, search_id, PipelineResult(source=JobSource.LINKEDIN))
                Events.publish(db, search_id, "search_completed", {
                    "search_id": str(search_id), "status": "completed", "total_discovered": 0,
                    "total_extracted": 0, "total_failed": 0,
                })
        return search_id

    yield create
    with SessionLocal.begin() as db:
        db.execute(delete(SearchTaskRecord).where(SearchTaskRecord.search_id.in_(ids)))


def url(search_id):
    return f"/api/v1/jobs/search/{search_id}/events"


def frames(response):
    return [dict(line.split(": ", 1) for line in block.splitlines()) for block in response.text.strip().split("\n\n")]


def test_nonexistent_search_returns_404_before_stream():
    response = TestClient(app).get(url(uuid4()))
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


def test_invalid_search_id_returns_422():
    assert TestClient(app).get(url("not-a-uuid")).status_code == 422


def test_sse_headers_format_order_and_terminal_close(search_factory):
    search_id = search_factory()
    response = TestClient(app).get(url(search_id))
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.text.endswith("\n\n")
    events = frames(response)
    assert [e["id"] for e in events] == ["1", "2", "3"]
    assert [e["event"] for e in events] == ["search_queued", "search_started", "search_completed"]
    assert json.loads(events[0]["data"]) == {"search_id": str(search_id), "status": "pending", "source": "linkedin"}


@pytest.mark.parametrize("params,headers,expected", [
    ({}, {"Last-Event-ID": "1"}, ["2", "3"]),
    ({"after": "2"}, {}, ["3"]),
    ({"after": "2"}, {"Last-Event-ID": "1"}, ["2", "3"]),
    ({"after": "0"}, {"Last-Event-ID": "2"}, ["3"]),
])
def test_replay_and_header_precedence(search_factory, params, headers, expected):
    response = TestClient(app).get(url(search_factory()), params=params, headers=headers)
    assert response.status_code == 200
    assert [e["id"] for e in frames(response)] == expected


@pytest.mark.parametrize("cursor", ["3", "4", "2147483647"])
def test_latest_or_future_cursor_closes_without_duplicates(search_factory, cursor):
    response = TestClient(app).get(url(search_factory()), headers={"Last-Event-ID": cursor})
    assert response.status_code == 200
    assert response.text == ""


@pytest.mark.parametrize("value", ["-1", "abc", "1.5", "", " 1", "+1", "2147483648", "9" * 100])
@pytest.mark.parametrize("mechanism", ["header", "query"])
def test_bad_cursor_is_client_error(search_factory, mechanism, value):
    kwargs = {"headers": {"Last-Event-ID": value}} if mechanism == "header" else {"params": {"after": value}}
    assert TestClient(app).get(url(search_factory()), **kwargs).status_code == 422


def test_overridden_cursor_is_still_validated(search_factory):
    response = TestClient(app).get(url(search_factory()), params={"after": "bad"}, headers={"Last-Event-ID": "1"})
    assert response.status_code == 422


@pytest.mark.parametrize("pages", [97, 98, 201])
def test_terminal_replay_drains_multiple_or_exact_batches(search_factory, pages):
    response = TestClient(app).get(url(search_factory(pages=pages)))
    events = frames(response)
    assert [int(e["id"]) for e in events] == list(range(1, pages + 4))
    assert events[-1]["event"] == "search_completed"


def test_failed_search_replays_and_closes(search_factory):
    search_id = search_factory(completed=False)

    def fail(source, request):
        raise RuntimeError("private browser information")

    JobQueueWorker(fail).run_once(search_id)
    response = TestClient(app).get(url(search_id))
    assert [e["event"] for e in frames(response)] == ["search_queued", "search_started", "search_failed"]
    assert "private browser information" not in response.text


class Connection:
    disconnected = False

    async def is_disconnected(self):
        return self.disconnected


def test_heartbeat_disconnect_and_session_free_wait(search_factory, monkeypatch):
    search_id = search_factory(completed=False)
    connection = Connection()
    sleeps = []
    checked_out = engine.pool.checkedout()
    monkeypatch.setattr(streaming, "HEARTBEAT_INTERVAL_SECONDS", 0)

    async def sleep(seconds):
        sleeps.append(seconds)
        assert engine.pool.checkedout() == checked_out
        connection.disconnected = True

    monkeypatch.setattr(streaming.asyncio, "sleep", sleep)

    async def collect():
        return [chunk async for chunk in streaming.stream_search_events(connection, search_id, 1)]

    assert asyncio.run(asyncio.wait_for(collect(), timeout=2)) == [": heartbeat\n\n"]
    assert sleeps == [1.0]


def test_reads_run_off_event_loop_and_disconnected_events_remain_replayable(search_factory, monkeypatch):
    search_id = search_factory(completed=False)
    connection = Connection()
    read_threads = []
    original = streaming.read_event_batch

    def reader(*args):
        read_threads.append(get_ident())
        return original(*args)

    monkeypatch.setattr(streaming, "read_event_batch", reader)

    async def first_connection():
        stream = streaming.stream_search_events(connection, search_id, 0)
        first = await anext(stream)
        connection.disconnected = True
        assert [chunk async for chunk in stream] == []
        return first

    first = asyncio.run(asyncio.wait_for(first_connection(), timeout=2))
    assert first.startswith("id: 1\nevent: search_queued\n")
    assert read_threads and all(thread != get_ident() for thread in read_threads)
    JobQueueWorker(lambda source, request: PipelineResult(source=source)).run_once(search_id)
    response = TestClient(app).get(url(search_id), headers={"Last-Event-ID": "1"})
    assert [e["id"] for e in frames(response)] == ["2", "3"]


def test_new_committed_events_are_delivered_on_next_poll(search_factory, monkeypatch):
    search_id = search_factory(completed=False)
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)
        assert len(sleeps) == 1
        # Publish on an independent session after the first empty read.
        await asyncio.to_thread(
            JobQueueWorker(lambda source, request: PipelineResult(source=source)).run_once,
            search_id,
        )

    monkeypatch.setattr(streaming.asyncio, "sleep", sleep)

    async def collect():
        return [chunk async for chunk in streaming.stream_search_events(Connection(), search_id, 1)]

    chunks = asyncio.run(asyncio.wait_for(collect(), timeout=2))
    assert [chunk.splitlines()[0] for chunk in chunks] == ["id: 2", "id: 3"]
    assert sleeps == [1.0]


def test_disconnect_before_poll_performs_no_database_read(monkeypatch):
    connection = Connection()
    connection.disconnected = True
    monkeypatch.setattr(streaming, "read_event_batch", lambda *args: pytest.fail("Unexpected database read"))

    async def collect():
        return [chunk async for chunk in streaming.stream_search_events(connection, uuid4(), 0)]

    assert asyncio.run(asyncio.wait_for(collect(), timeout=2)) == []


def test_deleted_search_closes_existing_stream(search_factory):
    search_id = search_factory(completed=False)
    with SessionLocal.begin() as db:
        db.execute(delete(SearchTaskRecord).where(SearchTaskRecord.search_id == search_id))

    async def collect():
        return [chunk async for chunk in streaming.stream_search_events(Connection(), search_id, 0)]

    assert asyncio.run(asyncio.wait_for(collect(), timeout=2)) == []


def test_utf8_and_newlines_are_valid_single_data_line(search_factory):
    search_id = search_factory()
    with SessionLocal.begin() as db:
        event = Events.publish(db, search_id, "job_extracted", {
            "job_url": "https://example.com/job", "title": "Développeur\nPython",
            "company": "例", "total_extracted": 1,
        })
    wire = streaming.format_event(event).encode("utf-8").decode("utf-8")
    assert len(wire.splitlines()) == 4
    assert json.loads(wire.splitlines()[2][6:])["title"] == "Développeur\nPython"


def test_cors_allows_reconnection_header():
    response = TestClient(app).options(url(uuid4()), headers={
        "Origin": settings.FRONTEND_URL,
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "Last-Event-ID",
    })
    assert response.status_code == 200
