
import pytest

from backend.app.schemas.job import (
    JobSearchRequest,
    JobSource,
    JobStatus,
)
from backend.app.services.job_pipeline import (
    JobExtractionPipeline,
)


pipeline = JobExtractionPipeline()


def make_job_html(title, company):
    return f"""
    <html>
      <head>
        <script type="application/ld+json">
        {{
          "@context": "https://schema.org",
          "@type": "JobPosting",
          "title": "{title}",
          "description": "<p>Full job description.</p>",
          "hiringOrganization": {{
            "@type": "Organization",
            "name": "{company}"
          }}
        }}
        </script>
      </head>
      <body></body>
    </html>
    """


def test_linkedin_pipeline():
    url1 = "https://www.linkedin.com/jobs/view/101/"
    url2 = "https://www.linkedin.com/jobs/view/202/"

    listing_html = """
    <a href="/jobs/view/101/">First</a>
    <a href="/jobs/view/202/">Second</a>
    <a href="/jobs/view/101/">Duplicate</a>
    """

    result = pipeline.run(
        source=JobSource.LINKEDIN,
        search=JobSearchRequest(date_posted="any", keyword="Python"),
        listing_html=listing_html,
        detail_pages={
            url1: make_job_html("Python Developer", "Company A"),
            url2: make_job_html("Backend Engineer", "Company B"),
        },
    )

    assert result.total_discovered == 2
    assert result.total_extracted == 2
    assert result.total_failed == 0

    assert result.jobs[0].title == "Python Developer"
    assert result.jobs[0].description == "Full job description."
    assert result.jobs[0].status == JobStatus.UNKNOWN


def test_wellfound_pipeline():
    url = "https://wellfound.com/jobs/12345-ai-engineer"

    listing_html = """
    <a href="/jobs/12345-ai-engineer">AI Engineer</a>
    """

    result = pipeline.run(
        source=JobSource.WELLFOUND,
        search=JobSearchRequest(date_posted="any", keyword="AI Engineer"),
        listing_html=listing_html,
        detail_pages={
            url: make_job_html("AI Engineer", "Startup A"),
        },
    )

    assert result.total_discovered == 1
    assert result.total_extracted == 1
    assert result.jobs[0].source == JobSource.WELLFOUND
    assert result.jobs[0].company == "Startup A"


def test_partial_extraction_failure():
    valid_url = "https://wellfound.com/jobs/12345-valid"
    invalid_url = "https://wellfound.com/jobs/67890-invalid"

    listing_html = """
    <a href="/jobs/12345-valid">Valid</a>
    <a href="/jobs/67890-invalid">Invalid</a>
    """

    result = pipeline.run(
        source=JobSource.WELLFOUND,
        search=JobSearchRequest(date_posted="any", keyword="Developer"),
        listing_html=listing_html,
        detail_pages={
            valid_url: make_job_html("Developer", "Startup B"),
            invalid_url: "<html><body></body></html>",
        },
    )

    assert result.total_discovered == 2
    assert result.total_extracted == 1
    assert result.total_failed == 1
    assert result.failures[0].job_url == invalid_url


def test_missing_detail_html():
    result = pipeline.run(
        source=JobSource.LINKEDIN,
        search=JobSearchRequest(date_posted="any", keyword="Python"),
        listing_html='<a href="/jobs/view/101/">Job</a>',
        detail_pages={},
    )

    assert result.total_discovered == 1
    assert result.total_extracted == 0
    assert result.total_failed == 1


def test_max_results():
    listing_html = """
    <a href="/jobs/view/101/">Job 1</a>
    <a href="/jobs/view/202/">Job 2</a>
    <a href="/jobs/view/303/">Job 3</a>
    """

    result = pipeline.run(
        source=JobSource.LINKEDIN,
        search=JobSearchRequest(
            date_posted="any",
            keyword="Developer",
            max_results=1,
        ),
        listing_html=listing_html,
        detail_pages={
            "https://www.linkedin.com/jobs/view/101/":
                make_job_html("Developer", "Company A"),
        },
    )

    assert result.total_discovered == 3
    assert result.total_extracted == 1
    assert result.total_failed == 0


def test_pipeline_fills_result_limit_after_date_exclusions(caplog):
    import logging
    from datetime import datetime, timezone

    first = "https://www.linkedin.com/jobs/view/101/"
    second = "https://www.linkedin.com/jobs/view/202/"
    third = "https://www.linkedin.com/jobs/view/303/"
    with caplog.at_level(logging.INFO):
        result = pipeline.run(
            source=JobSource.LINKEDIN,
            search=JobSearchRequest(keyword="Developer", max_results=1),
            listing_html=f'<a href="{first}">1</a><a href="{second}?trk=x">2</a><a href="{second}">dup</a><a href="{third}">3</a>',
            detail_pages={
                first: make_job_html("Undated", "Acme"),
                second + "?utm_source=test": make_job_html("Recent", "Acme").replace(
                    '"@type": "JobPosting",', '"@type": "JobPosting", "datePosted": "2026-10-08T10:00:00Z",',
                ),
            },
            now=datetime(2026, 10, 8, 12, tzinfo=timezone.utc),
        )
    assert result.discovered_urls == [first, second, third]
    assert result.total_extracted == 1
    assert result.total_failed == 0  # Third URL was discovered but intentionally not attempted.
    assert result.jobs[0].title == "Recent"
    assert "Excluded job" in caplog.text
