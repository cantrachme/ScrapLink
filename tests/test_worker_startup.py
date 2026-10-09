from contextlib import contextmanager
from threading import Event
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError

from backend.app.workers import run_worker
from backend.app.workers.fixture_site import FixtureSite
from backend.app.workers.queue_worker import JobQueueWorker


def test_help_does_not_open_browser_or_database(capsys):
    with pytest.raises(SystemExit) as exc:
        run_worker.main(["--help"])
    assert exc.value.code == 0
    assert "--mode" in capsys.readouterr().out


@pytest.mark.parametrize("arguments", [[], ["--mode", "fixture", "--poll-interval", "0"],
    ["--mode", "fixture", "--stale-timeout", "nan"], ["--mode", "fixture", "--max-pages", "0"]])
def test_invalid_cli_arguments(arguments):
    with pytest.raises(SystemExit) as exc:
        run_worker.main(arguments)
    assert exc.value.code == 2


def test_fixture_requires_development(monkeypatch):
    monkeypatch.setattr(run_worker.settings, "APP_ENV", "production")
    with pytest.raises(SystemExit):
        run_worker.main(["--mode", "fixture", "--once"])


@pytest.mark.parametrize("sources", ["", "linkedin,unapproved"])
def test_live_requires_explicit_authorization(monkeypatch, sources):
    monkeypatch.setattr(run_worker.settings, "AUTHORIZED_LIVE_SOURCES", sources)
    with pytest.raises(SystemExit):
        run_worker.main(["--mode", "live", "--once"])


def test_fixture_worker_startup_without_pending_tasks(monkeypatch, caplog):
    monkeypatch.setattr(run_worker.settings, "APP_ENV", "development")
    monkeypatch.setattr(run_worker.settings, "BROWSER_HEADLESS", False)
    actual_run_once = JobQueueWorker.run_once
    called = []
    def run_empty(self):
        assert self.collector.headless is False
        assert self.collector.listing_url_builder is run_worker.build_source_search_url
        called.append(True)
        return actual_run_once(self, uuid4())
    @contextmanager
    def server(port):
        yield FixtureSite("http://127.0.0.1:8765")
    monkeypatch.setattr(run_worker, "fixture_server", server)
    monkeypatch.setattr(JobQueueWorker, "run_once", run_empty)
    monkeypatch.setattr(JobQueueWorker, "recover_stale", lambda *args: 0)
    with caplog.at_level("INFO"):
        assert run_worker.main(["--mode", "fixture", "--once"]) == 0
    assert called == [True]
    assert "No pending searches" in caplog.text
    assert "Worker shutdown complete" in caplog.text


def test_idle_polling_and_database_error_wait_for_stop(monkeypatch):
    stop = Event()
    worker = JobQueueWorker(lambda *args: pytest.fail("No browser work"), stop_event=stop)
    attempts = []
    def failed_poll(*args):
        attempts.append(True)
        raise OperationalError("connection", {}, RuntimeError("offline"))
    monkeypatch.setattr(worker, "recover_stale", failed_poll)
    def wait(seconds):
        assert seconds == 0.5
        stop.set()
        return True
    monkeypatch.setattr(stop, "wait", wait)
    worker.run_forever(0.5)
    assert attempts == [True]


def test_sigterm_uses_cooperative_shutdown_and_restores_handlers(monkeypatch):
    handlers = {}
    def signal(sig, handler):
        handlers[sig] = handler
        return "original"
    monkeypatch.setattr(run_worker.signal, "signal", signal)
    monkeypatch.setattr(run_worker.settings, "AUTHORIZED_LIVE_SOURCES", "linkedin")
    def run(self, *args):
        assert not self.stop_event.is_set()
        handlers[run_worker.signal.SIGTERM](run_worker.signal.SIGTERM, None)
        assert self.stop_event.is_set()
    monkeypatch.setattr(JobQueueWorker, "run_forever", run)
    assert run_worker.main(["--mode", "live"]) == 0
    assert set(handlers.values()) == {"original"}


@pytest.mark.parametrize("url", ["https://evil.invalid/jobs/1", "http://www.linkedin.com/jobs/view/1/",
    "https://www.linkedin.com/jobs/view/123/", "http://127.0.0.1:8765/linkedin/detail-1.html"])
def test_fixture_resolver_rejects_non_catalog_urls(url):
    with pytest.raises(ValueError, match="fixture catalog"):
        FixtureSite("http://127.0.0.1:8765").resolve(url)


@pytest.mark.parametrize("url,allowed", [
    ("http://127.0.0.1:8765/linkedin/listing-1.html", True),
    ("https://www.linkedin.com/jobs/search/", False),
    ("http://127.0.0.1:8000/", False),
    ("http://localhost:8765/", False),
    ("http://user:password@127.0.0.1:8765/", False),
])
def test_fixture_request_guard_includes_subresources_and_redirects(url, allowed):
    route = Mock()
    route.request.url = url
    FixtureSite("http://127.0.0.1:8765").route_request(route)
    assert route.continue_.called is allowed
    assert route.abort.called is not allowed


def test_live_rejects_unrecognized_empty_html():
    from types import SimpleNamespace
    from backend.app.schemas.job import JobSearchRequest, JobSource
    from backend.app.workers.browser_collector import BrowserCollector
    @contextmanager
    def session(**kwargs):
        yield SimpleNamespace(fetch=lambda *a, **kw: SimpleNamespace(
            status=200, body=b"<h1>Unavailable</h1>", encoding="utf-8", url=a[0],
        ))
    collector = BrowserCollector(run_worker.build_source_search_url, session_factory=session, strict_listings=True)
    with pytest.raises(RuntimeError, match="Unrecognized"):
        collector(JobSource.LINKEDIN, JobSearchRequest(keyword="Python Developer"))


@pytest.mark.parametrize("source,keyword,location", [
    ("linkedin", "Accountant", "United States"),
    ("linkedin", "Python Developer", "London"),
    ("wellfound", "Software Engineer", "United States"),
])
def test_fixture_rejects_searches_unrelated_to_catalog(source, keyword, location):
    from backend.app.schemas.job import JobSearchRequest, JobSource
    request = JobSearchRequest(source=source, keyword=keyword, location=location)
    url = run_worker.build_source_search_url(JobSource(source), request)
    with pytest.raises(ValueError, match="Fixture searches support"):
        FixtureSite("http://127.0.0.1:8765").resolve(url)
