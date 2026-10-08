
from backend.app.sources.base import (
    normalize_source_job_url,
)


def test_linkedin_relative_job_url():
    result = normalize_source_job_url(
        href="/jobs/view/123456/",
        base_url="https://www.linkedin.com/jobs/search/",
        allowed_domains=("linkedin.com",),
    )

    assert result == (
        "https://www.linkedin.com/jobs/view/123456/"
    )


def test_wellfound_absolute_job_url():
    result = normalize_source_job_url(
        href="https://wellfound.com/jobs/98765#details",
        base_url="https://wellfound.com/jobs",
        allowed_domains=("wellfound.com",),
    )

    assert result == "https://wellfound.com/jobs/98765"


def test_reject_external_domain():
    result = normalize_source_job_url(
        href="https://linkedin.com.evil.example/jobs/123",
        base_url="https://www.linkedin.com/jobs/",
        allowed_domains=("linkedin.com",),
    )

    assert result is None


def test_reject_javascript_url():
    result = normalize_source_job_url(
        href="javascript:alert(1)",
        base_url="https://wellfound.com/jobs",
        allowed_domains=("wellfound.com",),
    )

    assert result is None


def test_reject_empty_url():
    result = normalize_source_job_url(
        href="",
        base_url="https://www.linkedin.com/jobs/",
        allowed_domains=("linkedin.com",),
    )

    assert result is None
