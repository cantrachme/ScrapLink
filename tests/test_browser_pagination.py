import json
import logging
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from backend.app.schemas.job import JobSearchRequest, JobSource
from backend.app.sources.pagination import build_paginated_search_url
from backend.app.sources.search_router import build_source_search_url
from backend.app.workers.browser_collector import BrowserCollector


NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW


class FakeResponse:
    def __init__(self, html, status=200, url=None):
        self.body = html.encode()
        self.encoding = "utf-8"
        self.status = status
        self.url = url or ""


class FakeSession:
    def __init__(self, pages, calls):
        self.pages = pages
        self.calls = calls
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def fetch(self, url, **kwargs):
        self.calls.append(url)
        assert kwargs == {"google_search": False, "timeout": 30000, "wait": 12}
        response = self.pages[url]
        return response if isinstance(response, FakeResponse) else FakeResponse(response)


def detail(posted="2026-10-08T10:00:00Z"):
    data = {
        "@type": "JobPosting", "title": "Python Developer",
        "hiringOrganization": {"name": "Acme", "sameAs": "https://example.com"},
        "description": "<p>Complete first paragraph.</p><p>Complete second paragraph.</p>",
        "jobLocation": {"address": {"addressLocality": "New York", "addressCountry": "US"}},
        "employmentType": "FULL_TIME", "jobLocationType": "TELECOMMUTE",
        "baseSalary": {"currency": "USD", "value": {"minValue": 120000, "maxValue": 180000, "unitText": "YEAR"}},
    }
    if posted is not None:
        data["datePosted"] = posted
    return '<script type="application/ld+json">' + json.dumps(data) + '</script>'


def listing(*urls):
    return "".join(f'<a href="{url}">Job</a>' for url in urls) or "<html>No more jobs</html>"


def job_url(source, job_id):
    if source == JobSource.LINKEDIN:
        return f"https://www.linkedin.com/jobs/view/{job_id}/"
    return f"https://wellfound.com/jobs/{job_id}-python-developer"


def make_collector(pages, calls, **options):
    sessions = []

    def factory(**kwargs):
        assert kwargs == {"headless": False, "real_chrome": True, "network_idle": False}
        session = FakeSession(pages, calls)
        sessions.append(session)
        return session

    collector = BrowserCollector(
        listing_url_builder=options.pop("listing_url_builder", build_source_search_url),
        session_factory=factory, wait_ms=12, **options,
    )
    return collector, sessions


def collect(collector, source, request):
    with patch("backend.app.workers.browser_collector.datetime", FixedDatetime):
        return collector(source, request)


@pytest.mark.parametrize("source", [JobSource.LINKEDIN, JobSource.WELLFOUND])
def test_multiple_pages_filter_dedupe_and_preserve_details(source, caplog):
    request = JobSearchRequest(source=source.value, keyword="Python Developer", max_results=2)
    first, second, third = [build_paginated_search_url(source, request, n) for n in (1, 2, 3)]
    old, undated, missing, broken, good1, good2, unused = [job_url(source, n) for n in range(1, 8)]
    duplicate = (
        "https://linkedin.com/jobs/view/python-developer-5?trk=again"
        if source == JobSource.LINKEDIN else "https://www.wellfound.com/jobs/5-new-slug?utm_source=again"
    )
    pages = {
        first: listing(old, old + "?trk=duplicate", undated, missing, broken, good1),
        second: listing(duplicate, missing + "?utm_source=again", old, good2, unused),
        old: detail("2026-10-06T12:00:00Z"), undated: detail(None),
        missing: FakeResponse("Not found", status=404), broken: "<h1>Missing company</h1>",
        good1: detail(), good2: detail("2026-10-08T15:30:00+05:30"),
    }
    calls = []
    collector, sessions = make_collector(pages, calls)
    adapter = collector.pipeline.adapters[source]
    with caplog.at_level(logging.INFO), patch.object(
        adapter, "extract_job_details", wraps=adapter.extract_job_details,
    ) as extract:
        result = collect(collector, source, request)
    assert result.discovered_urls == [old, undated, missing, broken, good1, good2, unused]
    assert result.total_discovered == 7
    assert result.total_extracted == 2
    assert result.total_failed == 2
    assert [failure.job_url for failure in result.failures] == [missing, broken]
    assert "HTTP 404" in result.failures[0].error
    assert [job.job_url for job in result.jobs] == [good1, good2]
    assert calls == [first, old, undated, missing, broken, good1, second, good2]
    assert third not in calls and unused not in calls
    assert len(sessions) == 1 and sessions[0].closed
    assert extract.call_count == 5  # old, undated, broken, good1, good2; each once
    assert caplog.text.count("Excluded job") == 2
    for job in result.jobs:
        assert job.description == "Complete first paragraph.\nComplete second paragraph."
        assert job.company_url == "https://example.com"
        assert job.location == "New York, US"  # A United States search must retain it.
        assert job.posted_at == datetime(2026, 10, 8, 10, tzinfo=timezone.utc)
        if source == JobSource.WELLFOUND:
            assert job.compensation.min_amount == 120000
            assert job.compensation.max_amount == 180000
            assert job.employment_type.value == "full_time"
            assert job.workplace_type.value == "remote"


@pytest.mark.parametrize("source", [JobSource.LINKEDIN, JobSource.WELLFOUND])
@pytest.mark.parametrize("ending", ["empty", "duplicates"])
def test_stops_when_next_page_has_no_new_jobs(source, ending):
    request = JobSearchRequest(source=source.value, keyword="Python Developer", date_posted="any")
    first, second = [build_paginated_search_url(source, request, n) for n in (1, 2)]
    url = job_url(source, 1)
    pages = {first: listing(url), url: detail(None), second: listing() if ending == "empty" else listing(url + "?utm_source=again")}
    calls = []
    collector, _ = make_collector(pages, calls)
    result = collect(collector, source, request)
    assert result.total_discovered == result.total_extracted == 1
    assert result.total_failed == 0
    assert calls == [first, url, second]


def test_max_pages_bounds_search_even_if_no_jobs_qualify():
    source = JobSource.LINKEDIN
    request = JobSearchRequest(keyword="Python Developer")
    pages = {}
    for n in (1, 2):
        pages[build_paginated_search_url(source, request, n)] = listing(job_url(source, n))
        pages[job_url(source, n)] = detail(None)
    calls = []
    collector, _ = make_collector(pages, calls, max_pages=2)
    result = collect(collector, source, request)
    assert result.total_discovered == 2
    assert result.total_extracted == result.total_failed == 0
    assert len(calls) == 4


def test_result_limit_applies_after_filtering_entire_listing():
    source = JobSource.LINKEDIN
    request = JobSearchRequest(keyword="Python Developer", max_results=1)
    first = build_paginated_search_url(source, request, 1)
    old, good, unused = [job_url(source, n) for n in (1, 2, 3)]
    calls = []
    collector, _ = make_collector({
        first: listing(old, good, unused), old: detail("2020-01-01"), good: detail(),
    }, calls)
    result = collect(collector, source, request)
    assert result.total_discovered == 3
    assert result.total_extracted == 1
    assert result.total_failed == 0
    assert result.jobs[0].job_url == good
    assert calls == [first, old, good]


@pytest.mark.parametrize("max_pages", [0, -1, True, "3", 2.5])
def test_invalid_max_pages(max_pages):
    with pytest.raises(ValueError, match="max_pages"):
        make_collector({}, [], max_pages=max_pages)


@pytest.mark.parametrize("response", [
    FakeResponse("Forbidden", status=403), FakeResponse("Rate limited", status=429),
    FakeResponse("<title>Just a moment...</title>"),
    FakeResponse("Sign in", url="https://www.linkedin.com/checkpoint/challenge"),
])
def test_inaccessible_listing_raises_and_closes_session(response):
    request = JobSearchRequest(keyword="Python Developer")
    first = build_source_search_url(JobSource.LINKEDIN, request)
    calls = []
    collector, sessions = make_collector({first: response}, calls)
    with pytest.raises(RuntimeError, match="HTTP|challenge"):
        collect(collector, JobSource.LINKEDIN, request)
    assert calls == [first]
    assert sessions[0].closed


def test_inaccessible_later_listing_is_not_silent_truncation():
    source = JobSource.LINKEDIN
    request = JobSearchRequest(keyword="Python Developer", date_posted="any")
    first, second = [build_paginated_search_url(source, request, n) for n in (1, 2)]
    url = job_url(source, 1)
    calls = []
    collector, _ = make_collector({first: listing(url), url: detail(), second: FakeResponse("Forbidden", status=403)}, calls)
    with pytest.raises(RuntimeError, match="HTTP 403"):
        collect(collector, source, request)
    assert calls == [first, url, second]


def test_custom_source_listing_preserves_its_query_parameters():
    first = "https://www.linkedin.com/jobs/search/?keywords=Python&custom=kept"
    second = first + "&start=25"
    url = job_url(JobSource.LINKEDIN, 1)
    calls = []
    collector, _ = make_collector({first: listing(url), url: detail(), second: listing()}, calls, listing_url_builder=lambda source, request: first)
    result = collect(collector, JobSource.LINKEDIN, JobSearchRequest(keyword="Python"))
    assert result.total_extracted == 1
    assert calls == [first, url, second]


def test_wellfound_jobs_application_is_rejected_before_browser_starts():
    collector, sessions = make_collector({}, [], listing_url_builder=lambda source, request: "https://wellfound.com/jobs")
    with pytest.raises(ValueError, match="public /role/"):
        collector(JobSource.WELLFOUND, JobSearchRequest(source="wellfound", keyword="Python Developer"))
    assert not sessions


@pytest.mark.parametrize("source", [JobSource.LINKEDIN, JobSource.WELLFOUND])
def test_progress_tracks_unique_discovery_accepted_jobs_and_real_failures(source):
    request = JobSearchRequest(source=source.value, keyword="Python Developer")
    first, second, third = [build_paginated_search_url(source, request, n) for n in (1, 2, 3)]
    good, old, undated, missing, broken = [job_url(source, n) for n in range(1, 6)]
    calls, events = [], []
    collector, sessions = make_collector({
        first: listing(good, old, undated, missing, broken),
        good: detail(), old: detail("2020-01-01"), undated: detail(None),
        missing: FakeResponse("Not found", status=404), broken: "<h1>Missing company</h1>",
        second: listing(good + "?tracking=again"),
    }, calls)
    with patch("backend.app.workers.browser_collector.datetime", FixedDatetime):
        result = collector.collect_with_progress(source, request, lambda name, data: events.append((name, data)))
    assert [name for name, _ in events] == [
        "page_discovered", "job_extracted", "job_failed", "job_failed", "page_discovered",
    ]
    assert events[0][1] == {"page_number": 1, "new_jobs_discovered": 5, "total_discovered": 5}
    assert events[-1][1] == {"page_number": 2, "new_jobs_discovered": 0, "total_discovered": 5}
    assert events[1][1] == {
        "job_url": good, "title": "Python Developer", "company": "Acme", "total_extracted": 1,
    }
    assert [data["total_failed"] for name, data in events if name == "job_failed"] == [1, 2]
    assert [data["job_url"] for name, data in events if name == "job_failed"] == [missing, broken]
    assert result.total_discovered == 5 and result.total_extracted == 1 and result.total_failed == 2
    assert calls.count(good) == 1 and third not in calls
    assert len(sessions) == 1 and sessions[0].closed


@pytest.mark.parametrize("fail_on", ["page_discovered", "job_extracted", "job_failed"])
def test_progress_callback_errors_propagate_and_close_browser(fail_on):
    source = JobSource.LINKEDIN
    request = JobSearchRequest(keyword="Python Developer", date_posted="any")
    first = build_paginated_search_url(source, request, 1)
    url = job_url(source, 1)
    collector, sessions = make_collector({
        first: listing(url), url: FakeResponse("Missing", status=404) if fail_on == "job_failed" else detail(),
    }, [])

    def progress(name, data):
        if name == fail_on:
            raise RuntimeError("Event persistence unavailable")

    with pytest.raises(RuntimeError, match="Event persistence unavailable"):
        collector.collect_with_progress(source, request, progress)
    assert sessions[0].closed
