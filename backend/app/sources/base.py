
from abc import ABC, abstractmethod
from urllib.parse import urljoin, urlsplit, urlunsplit

from scrapling.parser import Selector

from backend.app.schemas.job import (
    JobListing,
    JobSearchRequest,
    JobSource,
)


def normalize_source_job_url(
    href: str,
    base_url: str,
    allowed_domains: tuple[str, ...],
) -> str | None:
    """Normalize and validate a source job URL."""

    if not href or not href.strip():
        return None

    absolute_url = urljoin(base_url, href.strip())
    parsed = urlsplit(absolute_url)

    hostname = (parsed.hostname or "").lower()

    is_allowed = any(
        hostname == domain
        or hostname.endswith(f".{domain}")
        for domain in allowed_domains
    )

    if parsed.scheme != "https" or not is_allowed:
        return None

    # Remove fragment but retain query parameters.
    return urlunsplit((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.query,
        "",
    ))


class BaseJobSourceAdapter(ABC):
    """Common interface for job source integrations."""

    source: JobSource
    allowed_domains: tuple[str, ...]

    @abstractmethod
    def discover_job_urls(
        self,
        page: Selector,
        search: JobSearchRequest,
    ) -> list[str]:
        """Extract job URLs from a search results page."""
        ...

    @abstractmethod
    def extract_job_details(
        self,
        page: Selector,
        job_url: str,
    ) -> JobListing:
        """Extract complete details from one job page."""
        ...
