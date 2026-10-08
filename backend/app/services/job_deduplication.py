"""Conservative URL normalization and source-scoped job identity."""

import re
from collections.abc import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from backend.app.schemas.job import JobSource


LINKEDIN_JOB_PATH = re.compile(r"/jobs/view/(?:[^/]+-)?(\d+)/?$")
WELLFOUND_JOB_PATH = re.compile(r"/jobs/(\d+)(?:-[^/]+)?/?$")
TRACKING_PARAMETERS = {
    "trk", "trkinfo", "trackingid", "refid", "lipi", "midtoken",
    "gclid", "fbclid",
}


def extract_job_id(source: JobSource, url: str) -> str | None:
    """Trust numeric IDs only in recognized, source-owned detail paths."""
    parsed = urlsplit(url)
    domains = {
        JobSource.LINKEDIN: "linkedin.com",
        JobSource.WELLFOUND: "wellfound.com",
    }
    domain = domains.get(source)
    if (
        domain is None
        or parsed.scheme != "https"
        or parsed.hostname not in (domain, f"www.{domain}")
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
    ):
        return None
    pattern = LINKEDIN_JOB_PATH if source == JobSource.LINKEDIN else WELLFOUND_JOB_PATH
    match = pattern.fullmatch(parsed.path)
    return match.group(1) if match else None


def normalize_job_url(source: JobSource, url: str) -> str:
    """Canonicalize known jobs without discarding unknown query parameters.

    LinkedIn has a navigable numeric-ID route. Wellfound keeps the slug from
    the first URL because its detail pages may need it. Unrecognized URLs
    are left intact rather than guessing their identity or access semantics.
    """
    job_id = extract_job_id(source, url)
    if job_id is None:
        return url
    parsed = urlsplit(url)
    if source == JobSource.LINKEDIN:
        host, path = "www.linkedin.com", f"/jobs/view/{job_id}/"
    else:
        host, path = "wellfound.com", parsed.path.rstrip("/")
    params = [
        (key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in TRACKING_PARAMETERS
    ]
    return urlunsplit(("https", host, path, urlencode(params), ""))


def job_identity(source: JobSource, url: str) -> tuple[JobSource, str]:
    job_id = extract_job_id(source, url)
    return source, f"id:{job_id}" if job_id else f"url:{normalize_job_url(source, url)}"


def deduplicate_job_urls(source: JobSource, urls: Iterable[str]) -> list[str]:
    """Keep the first occurrence (and its navigable URL) in discovery order."""
    seen: set[tuple[JobSource, str]] = set()
    unique = []
    for url in urls:
        key = job_identity(source, url)
        if key not in seen:
            seen.add(key)
            unique.append(normalize_job_url(source, url))
    return unique
