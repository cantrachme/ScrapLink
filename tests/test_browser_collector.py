
from uuid import uuid4

from backend.app.schemas.job import (
    JobSearchRequest,
    JobSource,
)
from backend.app.workers.browser_collector import BrowserCollector


class FakeResponse:
    def __init__(self, html):
        self.body = html.encode("utf-8")
        self.encoding = "utf-8"
        self.status = 200


class FakeSession:
    def __init__(self, pages, calls):
        self.pages = pages
        self.calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def fetch(self, url, **kwargs):
        self.calls.append(url)

        if url not in self.pages:
            raise RuntimeError("Page unavailable")

        return FakeResponse(self.pages[url])


def make_fixture():
    job_id = uuid4().int
    job_url = f"https://www.linkedin.com/jobs/view/{job_id}/"
    listing_url = "http://127.0.0.1:8765/listing"

    listing_html = (
        f'<a href="/jobs/view/{job_id}/">View job</a>'
    )

    detail_html = """
    <html>
    <head>
      <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Python Developer",
        "description": "<p>Build Python APIs.</p>",
        "hiringOrganization": {
          "@type": "Organization",
          "name": "Example Company"
        }
      }
      </script>
    </head>
    <body></body>
    </html>
    """

    return job_url, listing_url, listing_html, detail_html


def make_collector(pages, calls, listing_url):
    return BrowserCollector(
        listing_url_builder=(
            lambda source, request: listing_url
        ),
        session_factory=(
            lambda **options: FakeSession(pages, calls)
        ),
        headless=False,
        real_chrome=True,
    )


def test_browser_collector_extracts_full_job():
    job_url, listing_url, listing_html, detail_html = (
        make_fixture()
    )

    calls = []
    pages = {
        listing_url: listing_html,
        job_url: detail_html,
    }

    collector = make_collector(
        pages,
        calls,
        listing_url,
    )

    result = collector(
        JobSource.LINKEDIN,
        JobSearchRequest(
            date_posted="any",
            keyword="Python Developer",
            source="linkedin",
        ),
    )

    assert result.total_discovered == 1
    assert result.total_extracted == 1
    assert result.total_failed == 0

    assert result.jobs[0].title == "Python Developer"
    assert result.jobs[0].company == "Example Company"
    assert "Build Python APIs" in result.jobs[0].description

    assert calls == [listing_url, job_url]


def test_browser_collector_records_missing_detail():
    job_url, listing_url, listing_html, _ = (
        make_fixture()
    )

    calls = []
    pages = {
        listing_url: listing_html,
    }

    collector = make_collector(
        pages,
        calls,
        listing_url,
    )

    result = collector(
        JobSource.LINKEDIN,
        JobSearchRequest(
            date_posted="any",
            keyword="Python Developer",
            source="linkedin",
        ),
    )

    assert result.total_discovered == 1
    assert result.total_extracted == 0
    assert result.total_failed == 1
    assert result.failures[0].job_url == job_url
