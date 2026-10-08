
import pytest
from scrapling.parser import Selector

from backend.app.schemas.job import (
    JobSearchRequest,
    JobSource,
    JobStatus,
)
from backend.app.sources.linkedin.adapter import (
    LinkedInJobAdapter,
)


adapter = LinkedInJobAdapter()


def test_discover_linkedin_jobs():
    html = """
    <html><body>
      <a href="/jobs/view/123456/">Job 1</a>
      <a href="/jobs/view/123456/">Duplicate</a>
      <a href="https://www.linkedin.com/jobs/view/987654/">
        Job 2
      </a>
      <a href="https://evil.example/jobs/view/111/">
        Invalid
      </a>
    </body></html>
    """

    page = Selector(content=html)

    jobs = adapter.discover_job_urls(
        page,
        JobSearchRequest(keyword="Python"),
    )

    assert len(jobs) == 2
    assert jobs[0].endswith("/123456/")
    assert jobs[1].endswith("/987654/")


def test_extract_structured_linkedin_job():
    html = """
    <html>
      <head>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "JobPosting",
          "title": "Senior Python Developer",
          "description": "<p>Build backend APIs.</p><p>Work with PostgreSQL.</p>",
          "datePosted": "2026-10-07",
          "hiringOrganization": {
            "@type": "Organization",
            "name": "Example Tech"
          },
          "jobLocation": {
            "address": {
              "addressLocality": "New York",
              "addressRegion": "NY",
              "addressCountry": "US"
            }
          }
        }
        </script>
      </head>
      <body></body>
    </html>
    """

    job = adapter.extract_job_details(
        Selector(content=html),
        "https://www.linkedin.com/jobs/view/123456/",
    )

    assert job.source == JobSource.LINKEDIN
    assert job.source_job_id == "123456"
    assert job.title == "Senior Python Developer"
    assert job.company == "Example Tech"
    assert job.location == "New York, NY, US"
    assert "Build backend APIs" in job.description
    assert "PostgreSQL" in job.description
    assert job.posted_date.isoformat() == "2026-10-07"
    assert job.status == JobStatus.UNKNOWN


def test_extract_html_fallback():
    html = """
    <html><body>
      <h1 class="top-card-layout__title">
        Backend Engineer
      </h1>
      <a class="topcard__org-name-link">
        Example Company
      </a>
      <div class="show-more-less-html__markup">
        <p>Develop Python services.</p>
        <p>Maintain production systems.</p>
      </div>
    </body></html>
    """

    job = adapter.extract_job_details(
        Selector(content=html),
        "https://www.linkedin.com/jobs/view/555555/",
    )

    assert job.title == "Backend Engineer"
    assert job.company == "Example Company"
    assert "Develop Python services" in job.description
    assert "Maintain production systems" in job.description


def test_invalid_job_url():
    with pytest.raises(ValueError):
        adapter.extract_job_details(
            Selector(content="<html></html>"),
            "https://evil.example/jobs/view/123/",
        )


def test_missing_required_fields():
    with pytest.raises(ValueError):
        adapter.extract_job_details(
            Selector(content="<html><body></body></html>"),
            "https://www.linkedin.com/jobs/view/123/",
        )
