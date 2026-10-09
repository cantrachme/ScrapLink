"""API -> real PostgreSQL queue -> collector/adapters -> results -> SSE.

Default tests replace only the browser transport. Opt-in Chrome tests use the
same fixture catalog over loopback, never platform requests.
"""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from threading import Event
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, text

from backend.app.database import SessionLocal, engine
from backend.app.main import app
from backend.app.models.job import Job
from backend.app.models.search import SearchTaskRecord
from backend.app.repositories.job_repository import JobRepository
from backend.app.repositories.search_event_repository import SearchEventRepository as Events
from backend.app.repositories.search_repository import SearchRepository as Searches
from backend.app.schemas.job import Compensation, JobListing, JobSource
from backend.app.sources.search_router import build_source_search_url
from backend.app.workers.browser_collector import BrowserCollector
from backend.app.workers.fixture_site import FixtureSite, fixture_server
from backend.app.workers.execution_lock import lock_key
from backend.app.workers.queue_worker import JobQueueWorker


@pytest.fixture
def workflow(monkeypatch):
    # Controlled HTML fixtures must not depend on permission for live scraping.
    from backend.app.config import settings
    monkeypatch.setattr(settings, "ACTIVE_JOBS_AUTHORIZATIONS", {})
    ids = []
    job_ids = tuple(str(uuid4().int) for _ in range(4))
    site = FixtureSite("http://127.0.0.1:8765", job_ids)
    calls, sessions = [], []

    class Session:
        def __enter__(self):
            sessions.append(self)
            self.closed = False
            return self

        def __exit__(self, *args):
            self.closed = True

        def fetch(self, url, **options):
            assert urlsplit(url).netloc == urlsplit(site.origin).netloc
            assert options["google_search"] is False
            calls.append(url)
            status, body = site.response(urlsplit(url).path)
            return SimpleNamespace(status=status, body=body, encoding="utf-8", url=url)

    client = TestClient(app)

    def create(source="linkedin", **overrides):
        payload = {"source": source, "keyword": "Python Developer", "location": "United States",
                   "date_posted": "any", "max_results": 20, **overrides}
        response = client.post("/api/v1/jobs/search", json=payload)
        assert response.status_code == 202
        search_id = UUID(response.json()["search_id"])
        ids.append(search_id)
        return search_id

    def collector(**overrides):
        return BrowserCollector(listing_url_builder=build_source_search_url,
                                session_factory=lambda **kwargs: Session(),
                                navigation_url_resolver=site.resolve, **overrides)

    yield SimpleNamespace(create=create, collector=collector, site=site, client=client,
                          calls=calls, sessions=sessions, job_ids=job_ids)
    client.close()
    with SessionLocal.begin() as db:
        db.execute(delete(SearchTaskRecord).where(SearchTaskRecord.search_id.in_(ids)))
        db.execute(delete(Job).where(Job.source_job_id.in_(job_ids)))


def path(search_id):
    return f"/api/v1/jobs/search/{search_id}"


def events(search_id):
    with SessionLocal() as db:
        return Events.get_after(db, search_id, 0)


def make_stale(search_id):
    with SessionLocal.begin() as db:
        task = Searches.get(db, search_id)
        task.updated_at = datetime.now(timezone.utc) - timedelta(minutes=10)


@pytest.mark.parametrize("source", ["linkedin", "wellfound"])
def test_complete_fixture_workflow_pagination_duplicates_details_replay(workflow, source):
    w = workflow
    search_id = w.create(source)
    assert w.client.get(path(search_id)).json()["status"] == "pending"
    worker = JobQueueWorker(w.collector())
    assert worker.run_once(search_id)
    assert not worker.run_once(search_id)
    saved = w.client.get(path(search_id) + "/results").json()
    assert saved["status"] == "completed"
    assert saved["source"] == source
    assert (saved["total_discovered"], saved["total_extracted"], saved["total_failed"]) == (4, 3, 1)
    assert len(saved["failures"]) == 1 and "HTTP 403" in saved["failures"][0]["error"]
    assert len({job["id"] for job in saved["jobs"]}) == 3
    assert len(w.sessions) == 1 and w.sessions[0].closed
    assert sum("/listing-" in url for url in w.calls) == 3
    assert len(w.calls) == len(set(w.calls)) == 7
    for job in saved["jobs"]:
        assert UUID(job["id"])
        assert job["title"].startswith("[DEMO] Python Developer")
        assert "End of complete demonstration description." in job["description"]
        assert job["company"] == "ScrapLink Demonstration Company"
        assert job["location"] == "New York, US"
        assert job["employment_type"] == "full_time" and job["workplace_type"] == "remote"
        assert job["compensation"]["min_amount"] == 120000
        assert w.client.get(f'/api/v1/jobs/{job["id"]}').json() == job
    task = w.client.get(path(search_id)).json()
    assert task["status"] == "completed"
    assert task["request"]["source"] == source and task["request"]["date_posted"] == "any"
    log = events(search_id)
    assert [e.sequence for e in log] == list(range(1, len(log) + 1))
    assert all(e.search_id == search_id for e in log)
    assert [e.event_type for e in log] == [
        "search_queued", "search_started", "page_discovered", "job_extracted", "job_extracted",
        "page_discovered", "job_extracted", "job_failed", "page_discovered", "search_completed",
    ]
    replay = w.client.get(path(search_id) + "/events")
    assert replay.headers["content-type"].startswith("text/event-stream")
    assert replay.text.count("event: search_completed") == 1
    assert "<html" not in replay.text and "<script" not in replay.text
    missed = w.client.get(path(search_id) + "/events", headers={"Last-Event-ID": "5"}).text
    assert "id: 5\n" not in missed and "id: 6\n" in missed
    assert missed.endswith(replay.text.split("id: 6\n", 1)[1])
    assert w.client.get(path(search_id) + f"/events?after={len(log)}").text == ""
    # New engine connections and API client simulate process-local state loss.
    engine.dispose()
    with TestClient(app) as restarted:
        assert restarted.get(path(search_id) + "/results").json() == saved
    repeated_id = w.create(source)
    assert worker.run_once(repeated_id)
    repeated = w.client.get(path(repeated_id) + "/results").json()
    assert {j["id"] for j in repeated["jobs"]} == {j["id"] for j in saved["jobs"]}


@pytest.mark.parametrize("source", ["linkedin", "wellfound"])
def test_date_filter_and_partial_upsert_preserve_complete_data(workflow, monkeypatch, source):
    class FixedDate(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 8, 12, tzinfo=timezone.utc)

    monkeypatch.setattr("backend.app.workers.browser_collector.datetime", FixedDate)
    search_id = workflow.create(source, date_posted="24h")
    assert JobQueueWorker(workflow.collector()).run_once(search_id)
    saved = workflow.client.get(path(search_id) + "/results").json()
    assert (saved["total_discovered"], saved["total_extracted"], saved["total_failed"]) == (4, 2, 1)
    original = saved["jobs"][0]
    with SessionLocal.begin() as db:
        updated = JobRepository.upsert(db, JobListing(
            source=JobSource(source), source_job_id=original["source_job_id"], job_url=original["job_url"],
            title=original["title"], company=original["company"], compensation=Compensation(min_amount=130000),
        ))
        assert str(updated.id) == original["id"]
    detail = workflow.client.get(f'/api/v1/jobs/{original["id"]}').json()
    assert detail["description"] == original["description"]
    assert detail["employment_type"] == original["employment_type"]
    assert detail["compensation"] == {**original["compensation"], "min_amount": 130000}
    # A contradictory partial bound must not create an invalid salary range.
    # Changing currency must not carry old amounts into the new currency.
    for incoming, expected_min, expected_max, currency in [
        (Compensation(max_amount=50000), None, 50000, "USD"),
        (Compensation(currency="EUR", min_amount=60000), 60000, None, "EUR"),
    ]:
        with SessionLocal.begin() as db:
            JobRepository.upsert(db, JobListing(
                source=JobSource(source), source_job_id=original["source_job_id"], job_url=original["job_url"],
                title=original["title"], company=original["company"], compensation=incoming,
            ))
        response = workflow.client.get(f'/api/v1/jobs/{original["id"]}')
        assert response.status_code == 200
        salary = response.json()["compensation"]
        assert (salary["min_amount"], salary["max_amount"], salary["currency"]) == (expected_min, expected_max, currency)


@pytest.mark.parametrize("failure", ["launch", "listing_timeout", "details", "access_gate", "invalid_source"])
def test_failed_search_terminal_event_and_failure_audit(workflow, monkeypatch, failure):
    search_id = workflow.create()
    collector = workflow.collector()
    if failure == "launch":
        def fail(**kwargs):
            raise RuntimeError("Browser launch failed")
        collector.session_factory = fail
    elif failure == "invalid_source":
        def bad_source(*args):
            raise ValueError("Authorized source configuration is missing")
        collector.listing_url_builder = bad_source
    else:
        original = workflow.site.response
        def response(url):
            if failure == "listing_timeout":
                raise TimeoutError("Fixture page timeout")
            if failure == "details" and "detail-" in url:
                return 403, b"Denied"
            if failure == "access_gate":
                return 200, b"<title>Access denied</title>"
            return original(url)
        monkeypatch.setattr(workflow.site, "response", response)
    worker = JobQueueWorker(collector)
    assert worker.run_once(search_id)
    assert not worker.run_once(search_id)
    assert worker.recover_stale(1, search_id=search_id) == 0
    task = workflow.client.get(path(search_id)).json()
    assert task["status"] == "failed"
    if failure == "invalid_source":
        assert task["error"] == "ValueError: Authorized source configuration is missing"
        assert workflow.calls == []
    saved = workflow.client.get(path(search_id) + "/results").json()
    assert saved["jobs"] == []
    if failure == "details":
        assert saved["total_failed"] == 4 and len(saved["failures"]) == 4
    names = [e.event_type for e in events(search_id)]
    assert names.count("search_failed") == 1 and "search_completed" not in names
    assert workflow.client.get(path(search_id) + "/events").text.count("event: search_failed") == 1


def test_competing_workers_cannot_claim_or_recover_active_task(workflow):
    search_id = workflow.create()
    entered, finish = Event(), Event()
    collector = workflow.collector()
    def slow(source, request):
        entered.set()
        assert finish.wait(5)
        return collector(source, request)
    with ThreadPoolExecutor(max_workers=1) as pool:
        active = pool.submit(JobQueueWorker(slow).run_once, search_id)
        try:
            assert entered.wait(5)
            key = lock_key(search_id) & ((1 << 64) - 1)
            with SessionLocal() as db:
                lock_owner = db.execute(text("""
                    SELECT a.state, a.xact_start FROM pg_locks l
                    JOIN pg_stat_activity a ON a.pid = l.pid
                    WHERE l.locktype = 'advisory' AND l.granted
                    AND l.classid = :high AND l.objid = :low AND l.objsubid = 1
                """), {"high": key >> 32, "low": key & 0xffffffff}).one()
                assert lock_owner.state == "idle" and lock_owner.xact_start is None
            make_stale(search_id)
            competitor = JobQueueWorker(lambda *args: pytest.fail("Task was stolen"))
            assert not competitor.run_once(search_id)
            assert competitor.recover_stale(1, search_id=search_id) == 0
        finally:
            finish.set()
        assert active.result(timeout=5)
    assert [e.event_type for e in events(search_id)].count("search_started") == 1


def test_operator_shutdown_retains_progress_and_marks_failure(workflow):
    search_id = workflow.create()
    stop = Event()
    collector = workflow.collector()
    class Interrupted:
        def collect_with_progress(self, source, request, progress):
            def callback(name, payload):
                progress(name, payload)
                if name == "page_discovered":
                    stop.set()
            return collector.collect_with_progress(source, request, callback)
    worker = JobQueueWorker(Interrupted(), stop_event=stop)
    assert worker.run_once(search_id)
    assert [e.event_type for e in events(search_id)] == [
        "search_queued", "search_started", "page_discovered", "search_failed",
    ]
    assert "stopped by operator" in workflow.client.get(path(search_id)).json()["error"]
    assert not worker.run_once(search_id)


def test_process_crash_and_concurrent_recovery_once(workflow):
    search_id = workflow.create()
    # Abrupt exit skips finally blocks, as a killed worker would. PostgreSQL
    # releases connection ownership; no browser or platform traffic is involved.
    code = '''import os, sys
from uuid import UUID
from backend.app.workers.queue_worker import JobQueueWorker
class Crash:
    def collect_with_progress(self, source, request, progress):
        progress("page_discovered", {"page_number": 1, "new_jobs_discovered": 2, "total_discovered": 2})
        os._exit(23)
JobQueueWorker(Crash()).run_once(UUID(sys.argv[1]))
'''
    crashed = subprocess.run([sys.executable, "-c", code, str(search_id)], capture_output=True, timeout=10)
    assert crashed.returncode == 23
    assert workflow.client.get(path(search_id)).json()["status"] == "running"
    worker = JobQueueWorker(lambda *args: pytest.fail("Abandoned task must not be retried"))
    assert worker.recover_stale(search_id=search_id) == 0  # grace period
    make_stale(search_id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker.recover_stale, 1, search_id=search_id) for _ in range(2)]
        assert sum(f.result(timeout=5) for f in futures) == 1
    assert not worker.run_once(search_id)
    assert [e.event_type for e in events(search_id)] == [
        "search_queued", "search_started", "page_discovered", "search_failed",
    ]
    assert "abandoned" in workflow.client.get(path(search_id)).json()["error"]


def test_recovery_event_failure_rolls_back_status(workflow, monkeypatch):
    search_id = workflow.create()
    with SessionLocal.begin() as db:
        Searches.claim_next_pending(db, search_id)
    make_stale(search_id)
    worker = JobQueueWorker(workflow.collector())
    def fail(*args):
        raise RuntimeError("Cannot persist terminal event")
    monkeypatch.setattr(worker.events, "publish", fail)
    with pytest.raises(RuntimeError, match="terminal event"):
        worker.recover_stale(1, search_id=search_id)
    assert workflow.client.get(path(search_id)).json()["status"] == "running"
    assert [e.event_type for e in events(search_id)] == ["search_queued"]


@pytest.mark.parametrize("late_progress", [True, False])
def test_late_collector_cannot_write_after_ownership_loss_and_recovery(workflow, monkeypatch, late_progress):
    from backend.app.services.job_pipeline import PipelineResult
    search_id = workflow.create()
    @contextmanager
    def lost_lock(search_id):
        # Model a disconnected ownership connection while browser work was
        # in flight. Task state must fence both progress and final results.
        yield
    monkeypatch.setattr("backend.app.workers.queue_worker.execution_lock", lost_lock)
    recovery = JobQueueWorker(lambda *args: pytest.fail("Never retry"))
    class LateCollector:
        def collect_with_progress(self, source, request, progress):
            make_stale(search_id)
            assert recovery.recover_stale(1, search_id=search_id) == 1
            if late_progress:
                progress("page_discovered", {"page_number": 1, "new_jobs_discovered": 0, "total_discovered": 0})
            return PipelineResult(source=source)
    assert JobQueueWorker(LateCollector()).run_once(search_id)
    assert [e.event_type for e in events(search_id)] == ["search_queued", "search_started", "search_failed"]


@pytest.mark.browser
@pytest.mark.skipif(os.environ.get("SCRAPLINK_BROWSER_TESTS") != "1", reason="Opt-in real Chrome fixture test")
@pytest.mark.parametrize("source", ["linkedin", "wellfound"])
def test_real_chrome_fixture_workflow(workflow, source):
    search_id = workflow.create(source)
    with fixture_server(0, job_ids=workflow.job_ids) as site:
        collector = BrowserCollector(build_source_search_url, session_factory=site.browser_session,
                                     navigation_url_resolver=site.resolve, headless=True)
        assert JobQueueWorker(collector).run_once(search_id)
    saved = workflow.client.get(path(search_id) + "/results").json()
    assert saved["status"] == "completed"
    assert (saved["total_extracted"], saved["total_failed"]) == (3, 1)
    assert events(search_id)[-1].event_type == "search_completed"


@pytest.mark.browser
@pytest.mark.skipif(os.environ.get("SCRAPLINK_BROWSER_TESTS") != "1", reason="Opt-in real Chrome fixture test")
def test_real_chrome_blocks_external_subresources(workflow, monkeypatch):
    with fixture_server(0, job_ids=workflow.job_ids) as site:
        original = site.response
        def response(url):
            status, body = original(url)
            return status, body + b'<img src="https://scraplink-network-test.invalid/image.png">'
        monkeypatch.setattr(site, "response", response)
        rejected, completed = [], []
        original_route = site.route_request
        def route(request):
            if urlsplit(request.request.url).netloc != urlsplit(site.origin).netloc:
                rejected.append(request.request.url)
            original_route(request)
        monkeypatch.setattr(site, "route_request", route)
        with site.browser_session(headless=True, real_chrome=True, network_idle=False) as session:
            session.context.on("requestfinished", lambda req: completed.append(req.url))
            result = session.fetch(site.origin + "/linkedin/listing-1.html", google_search=False)
            assert result.status == 200
            # The HTTP fixture's CSP blocks the first image before routing.
            # Also exercise the route independently of CSP in the same context.
            page = session.context.new_page()
            page.set_content('<img src="https://scraplink-network-test.invalid/image.png">')
            page.close()
        assert rejected == ["https://scraplink-network-test.invalid/image.png"]
        assert completed and all(url.startswith(site.origin + "/") for url in completed)
