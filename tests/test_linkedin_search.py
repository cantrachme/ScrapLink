
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest

from backend.app.schemas.job import (
    JobSearchRequest,
    JobSource,
)
from backend.app.sources.linkedin.search import (
    build_linkedin_search_url,
)
from backend.app.workers.browser_collector import (
    BrowserCollector,
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
            raise RuntimeError("Page not found")

        return FakeResponse(self.pages[url])


def test_linkedin_search_url_filters():
    request = JobSearchRequest(
        source="linkedin",
        keyword="Senior Python Developer",
        location="United States",
        date_posted="24h",
        max_results=20,
    )

    url = build_linkedin_search_url(
        JobSource.LINKEDIN,
        request,
    )

    parsed = urlsplit(url)
    params = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "www.linkedin.com"
    assert parsed.path == "/jobs/search/"

    assert params["keywords"] == [
        "Senior Python Developer"
    ]
    assert params["location"] == ["United States"]
    assert params["f_TPR"] == ["r86400"]
    assert params["sortBy"] == ["DD"]



def test_linkedin_search_url_with_default_filters():
    request = JobSearchRequest(
        source="linkedin",
        keyword="Backend Engineer",
    )

    url = build_linkedin_search_url(
        JobSource.LINKEDIN,
        request,
    )

    params = parse_qs(urlsplit(url).query)

    assert params["keywords"] == ["Backend Engineer"]
    assert params["location"] == ["United States"]
    assert params["f_TPR"] == ["r86400"]
    assert params["sortBy"] == ["DD"]



def test_linkedin_builder_rejects_other_source():
    request = JobSearchRequest(
        source="wellfound",
        keyword="Python Developer",
    )

    with pytest.raises(ValueError):
        build_linkedin_search_url(
            JobSource.WELLFOUND,
            request,
        )


def test_linkedin_search_and_detail_discovery():
    request = JobSearchRequest(
        source="linkedin",
        keyword="Python Developer",
        date_posted="24h",
    )

    search_url = build_linkedin_search_url(
        JobSource.LINKEDIN,
        request,
    )

    job_id = uuid4().int
    job_url = (
        f"https://www.linkedin.com/jobs/view/{job_id}/"
    )

    listing_html = f"""
    <html>
      <body>
        <a href="/jobs/view/{job_id}/">
          Python Developer
        </a>
      </body>
    </html>
    """

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

    visited = []

    pages = {
        search_url: listing_html,
        job_url: detail_html,
    }

    collector = BrowserCollector(
        listing_url_builder=build_linkedin_search_url,
        session_factory=lambda **kwargs: FakeSession(
            pages,
            visited,
        ),
        headless=False,
        real_chrome=True,
    )

    result = collector(
        JobSource.LINKEDIN,
        request,
    )

    assert result.total_discovered == 1
    assert result.total_extracted == 1
    assert result.total_failed == 0

    assert result.jobs[0].title == "Python Developer"
    assert result.jobs[0].company == "Example Company"
    assert "Build Python APIs" in result.jobs[0].description

    assert visited == [search_url, job_url]
