
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest

from backend.app.schemas.job import JobSearchRequest, JobSource
from backend.app.sources.search_router import build_source_search_url
from backend.app.sources.wellfound.search import (
    build_wellfound_search_url,
)
from backend.app.workers.browser_collector import BrowserCollector


def make_request(**overrides):
    values = {
        "source": "wellfound",
        "keyword": "Python Developer",
        "location": "United States",
        "date_posted": "any",
    }
    values.update(overrides)
    return JobSearchRequest(**values)


def test_wellfound_role_location_url():
    url = build_wellfound_search_url(
        JobSource.WELLFOUND,
        make_request(),
    )

    assert url == (
        "https://wellfound.com/role/l/"
        "python-developer/united-states"
    )


def test_wellfound_role_without_location():
    url = build_wellfound_search_url(
        JobSource.WELLFOUND,
        make_request(location=""),
    )

    assert url == "https://wellfound.com/role/python-developer"


def test_wellfound_date_filter_is_applied_after_extraction():
    assert build_wellfound_search_url(
        JobSource.WELLFOUND, make_request(date_posted="24h"),
    ) == build_wellfound_search_url(JobSource.WELLFOUND, make_request())


def test_wellfound_rejects_unknown_role():
    with pytest.raises(ValueError, match="Unsupported Wellfound role"):
        build_wellfound_search_url(
            JobSource.WELLFOUND,
            make_request(keyword="Unmapped Role"),
        )


def test_source_router_selects_platform():
    linkedin = JobSearchRequest(
        source="linkedin",
        keyword="Python Developer",
    )

    wellfound = make_request()

    linkedin_url = build_source_search_url(
        JobSource.LINKEDIN, linkedin
    )

    wellfound_url = build_source_search_url(
        JobSource.WELLFOUND, wellfound
    )

    assert urlsplit(linkedin_url).hostname == "www.linkedin.com"
    assert urlsplit(wellfound_url).hostname == "wellfound.com"

    assert parse_qs(urlsplit(linkedin_url).query)["keywords"] == [
        "Python Developer"
    ]


def test_wellfound_rejects_wrong_source():
    with pytest.raises(ValueError):
        build_wellfound_search_url(
            JobSource.LINKEDIN,
            make_request(),
        )


class FakeResponse:
    def __init__(self, html):
        self.status = 200
        self.encoding = "utf-8"
        self.body = html.encode("utf-8")


class FakeSession:
    def __init__(self, pages, visited):
        self.pages = pages
        self.visited = visited

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def fetch(self, url, **kwargs):
        self.visited.append(url)
        if url not in self.pages:
            raise RuntimeError("Page unavailable")
        return FakeResponse(self.pages[url])


def test_wellfound_collector_integration():
    request = make_request()

    listing_url = build_source_search_url(
        JobSource.WELLFOUND, request
    )

    job_id = uuid4().int
    job_url = (
        f"https://wellfound.com/jobs/"
        f"{job_id}-python-developer"
    )

    listing_html = (
        f'<a href="/jobs/{job_id}-python-developer">'
        "Python Developer</a>"
    )

    detail_html = """
    <html>
      <head>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "JobPosting",
          "title": "Python Developer",
          "description": "<p>Build startup software.</p>",
          "hiringOrganization": {
            "@type": "Organization",
            "name": "Example Startup"
          }
        }
        </script>
      </head>
      <body></body>
    </html>
    """

    pages = {
        listing_url: listing_html,
        job_url: detail_html,
    }
    visited = []

    collector = BrowserCollector(
        listing_url_builder=build_source_search_url,
        session_factory=lambda **kwargs: FakeSession(
            pages, visited
        ),
        max_pages=1,
        headless=False,
        real_chrome=True,
    )

    result = collector(JobSource.WELLFOUND, request)

    assert result.total_discovered == 1
    assert result.total_extracted == 1
    assert result.total_failed == 0
    assert result.jobs[0].title == "Python Developer"
    assert result.jobs[0].company == "Example Startup"
    assert "Build startup software" in result.jobs[0].description
    assert visited == [listing_url, job_url]
