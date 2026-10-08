import pytest

from backend.app.schemas.job import JobSource
from backend.app.services.job_deduplication import (
    deduplicate_job_urls, extract_job_id, job_identity, normalize_job_url,
)


@pytest.mark.parametrize("source,urls,expected", [
    (JobSource.LINKEDIN, [
        "https://www.linkedin.com/jobs/view/123456/",
        "https://www.linkedin.com/jobs/view/123456/?trk=public_jobs#details",
        "https://linkedin.com/jobs/view/python-developer-at-acme-123456?refId=abc",
    ], "https://www.linkedin.com/jobs/view/123456/"),
    (JobSource.WELLFOUND, [
        "https://wellfound.com/jobs/123456-python-developer?utm_source=test",
        "https://www.wellfound.com/jobs/123456-python-developer/#details",
        "https://wellfound.com/jobs/123456-another-slug",
        "https://wellfound.com/jobs/123456",
    ], "https://wellfound.com/jobs/123456-python-developer"),
])
def test_tracking_and_recognized_formats_share_identity(source, urls, expected):
    assert deduplicate_job_urls(source, urls) == [expected]
    assert {extract_job_id(source, url) for url in urls} == {"123456"}
    assert len({job_identity(source, url) for url in urls}) == 1


def test_sources_never_share_identity():
    assert job_identity(JobSource.LINKEDIN, "https://linkedin.com/jobs/view/123/") != job_identity(
        JobSource.WELLFOUND, "https://wellfound.com/jobs/123-engineer",
    )


def test_unknown_query_parameters_and_wellfound_slug_survive():
    assert normalize_job_url(
        JobSource.WELLFOUND,
        "https://wellfound.com/jobs/123-python-developer?utm_campaign=test&access=abc&lang=en#top",
    ) == "https://wellfound.com/jobs/123-python-developer?access=abc&lang=en"
    assert normalize_job_url(
        JobSource.LINKEDIN,
        "https://linkedin.com/jobs/view/title-123?trk=test&token=abc",
    ) == "https://www.linkedin.com/jobs/view/123/?token=abc"


def test_first_discovery_order_is_preserved():
    urls = [f"https://wellfound.com/jobs/{value}" for value in ["3-first", "1-second", "3-duplicate", "2-third"]]
    assert deduplicate_job_urls(JobSource.WELLFOUND, urls) == [urls[0], urls[1], urls[3]]


@pytest.mark.parametrize("url", [
    "https://evil.example/jobs/view/123/",
    "https://linkedin.com.evil.example/jobs/view/123/",
    "https://www.linkedin.com/jobs/search/?currentJobId=123",
    "https://www.linkedin.com/jobs/view/not-an-id",
    "https://user@www.linkedin.com/jobs/view/123/",
])
def test_unrecognized_urls_do_not_gain_trusted_ids(url):
    assert extract_job_id(JobSource.LINKEDIN, url) is None
    assert normalize_job_url(JobSource.LINKEDIN, url) == url
