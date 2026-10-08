
import pytest
from scrapling.parser import Selector

from backend.app.schemas.job import (
    EmploymentType,
    JobSearchRequest,
    JobSource,
    JobStatus,
    WorkplaceType,
)
from backend.app.sources.wellfound.adapter import (
    WellfoundJobAdapter,
)


adapter = WellfoundJobAdapter()


def test_discover_wellfound_jobs():
    html = """
    <html><body>
      <a href="/jobs/12345-python-developer">Job 1</a>
      <a href="/jobs/12345-python-developer">Duplicate</a>
      <a href="https://wellfound.com/jobs/67890-ai-engineer">
        Job 2
      </a>
      <a href="https://evil.example/jobs/111">Invalid</a>
    </body></html>
    """

    urls = adapter.discover_job_urls(
        Selector(content=html),
        JobSearchRequest(keyword="Python"),
    )

    assert len(urls) == 2
    assert urls[0].endswith("12345-python-developer")
    assert urls[1].endswith("67890-ai-engineer")


def test_extract_structured_wellfound_job():
    html = """
    <html><head>
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "JobPosting",
      "title": "Senior AI Engineer",
      "description": "<p>Build AI systems.</p><p>Deploy models.</p>",
      "datePosted": "2026-10-07",
      "employmentType": "FULL_TIME",
      "jobLocationType": "TELECOMMUTE",
      "hiringOrganization": {
        "@type": "Organization",
        "name": "Example AI Startup"
      },
      "baseSalary": {
        "@type": "MonetaryAmount",
        "currency": "USD",
        "value": {
          "@type": "QuantitativeValue",
          "minValue": 120000,
          "maxValue": 180000,
          "unitText": "YEAR"
        }
      }
    }
    </script>
    </head><body></body></html>
    """

    job = adapter.extract_job_details(
        Selector(content=html),
        "https://wellfound.com/jobs/12345-senior-ai-engineer",
    )

    assert job.source == JobSource.WELLFOUND
    assert job.source_job_id == "12345"
    assert job.title == "Senior AI Engineer"
    assert job.company == "Example AI Startup"
    assert "Build AI systems" in job.description
    assert "Deploy models" in job.description
    assert job.employment_type == EmploymentType.FULL_TIME
    assert job.workplace_type == WorkplaceType.REMOTE
    assert job.compensation.min_amount == 120000
    assert job.compensation.max_amount == 180000
    assert job.compensation.period == "year"
    assert job.posted_date.isoformat() == "2026-10-07"
    assert job.status == JobStatus.UNKNOWN


def test_extract_html_fallback():
    html = """
    <html><body>
      <h1>Backend Python Developer</h1>
      <a href="/company/example-startup">
        Example Startup
      </a>
      <span data-testid="job-location">San Francisco</span>
      <span data-testid="employment-type">Full Time</span>
      <span data-testid="remote-work-policy">Hybrid</span>

      <div data-testid="job-skills">
        <ul>
          <li>Python</li>
          <li>FastAPI</li>
          <li>PostgreSQL</li>
        </ul>
      </div>

      <section aria-label="About the job">
        <p>Build scalable backend services.</p>
        <p>Maintain production APIs.</p>
      </section>
    </body></html>
    """

    job = adapter.extract_job_details(
        Selector(content=html),
        "https://wellfound.com/jobs/98765-backend-developer",
    )

    assert job.title == "Backend Python Developer"
    assert job.company == "Example Startup"
    assert job.location == "San Francisco"
    assert job.employment_type == EmploymentType.FULL_TIME
    assert job.workplace_type == WorkplaceType.HYBRID
    assert job.skills == [
        "Python", "FastAPI", "PostgreSQL"
    ]
    assert "Build scalable backend services" in job.description
    assert "Maintain production APIs" in job.description


def test_invalid_job_url():
    with pytest.raises(ValueError):
        adapter.extract_job_details(
            Selector(content="<html></html>"),
            "https://evil.example/jobs/12345",
        )


def test_missing_required_fields():
    with pytest.raises(ValueError):
        adapter.extract_job_details(
            Selector(content="<html><body></body></html>"),
            "https://wellfound.com/jobs/12345",
        )
