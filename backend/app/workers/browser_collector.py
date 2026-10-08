
import logging
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from scrapling.fetchers import DynamicSession

from backend.app.schemas.job import JobSearchRequest, JobSource
from backend.app.services.job_pipeline import (
    JobExtractionPipeline,
    PipelineResult,
)


logger = logging.getLogger(__name__)

ListingURLBuilder = Callable[[JobSource, JobSearchRequest], str]
DetailURLBuilder = Callable[[JobSource, str], str]


class BrowserCollector:
    """
    Collect job listing and detail HTML using Scrapling.

    URL builders are injected so the same collector can
    work with controlled fixtures and permitted job sources.
    """

    def __init__(
        self,
        listing_url_builder: ListingURLBuilder,
        detail_url_builder: DetailURLBuilder | None = None,
        *,
        session_factory: Callable[..., Any] = DynamicSession,
        headless: bool = False,
        real_chrome: bool = True,
        wait_ms: int = 0,
    ):
        self.listing_url_builder = listing_url_builder
        self.detail_url_builder = (
            detail_url_builder
            or (lambda source, job_url: job_url)
        )
        self.session_factory = session_factory
        self.headless = headless
        self.real_chrome = real_chrome
        self.wait_ms = wait_ms
        self.pipeline = JobExtractionPipeline()

    @staticmethod
    def _is_allowed_job_url(
        source: JobSource,
        job_url: str,
    ) -> bool:
        parsed = urlsplit(job_url)

        if parsed.scheme != "https":
            return False

        allowed_hosts = {
            JobSource.LINKEDIN: {
                "linkedin.com",
                "www.linkedin.com",
            },
            JobSource.WELLFOUND: {
                "wellfound.com",
                "www.wellfound.com",
            },
        }

        return parsed.hostname in allowed_hosts[source]

    def _fetch_html(self, session: Any, url: str) -> str:
        response = session.fetch(
            url,
            google_search=False,
            timeout=30000,
            wait=self.wait_ms,
        )

        if response.status >= 400:
            raise RuntimeError(
                f"Browser received HTTP {response.status}"
            )

        return response.body.decode(
            response.encoding or "utf-8",
            errors="replace",
        )

    def __call__(
        self,
        source: JobSource,
        search: JobSearchRequest,
    ) -> PipelineResult:
        listing_url = self.listing_url_builder(source, search)

        with self.session_factory(
            headless=self.headless,
            real_chrome=self.real_chrome,
            network_idle=False,
        ) as session:
            listing_html = self._fetch_html(
                session,
                listing_url,
            )

            # First pass: discover job URLs using the
            # existing platform-specific extraction pipeline.
            discovery = self.pipeline.run(
                source=source,
                search=search,
                listing_html=listing_html,
                detail_pages={},
            )

            job_urls = list(
                dict.fromkeys(discovery.discovered_urls)
            )[:search.max_results]

            detail_pages = {}

            for job_url in job_urls:
                if not self._is_allowed_job_url(
                    source, job_url
                ):
                    logger.warning(
                        "Skipping unexpected job URL: %s",
                        job_url,
                    )
                    continue

                try:
                    fetch_url = self.detail_url_builder(
                        source,
                        job_url,
                    )

                    detail_pages[job_url] = (
                        self._fetch_html(
                            session,
                            fetch_url,
                        )
                    )

                except Exception:
                    # Missing pages will be recorded as
                    # extraction failures by the pipeline.
                    logger.exception(
                        "Failed to fetch job: %s",
                        job_url,
                    )

            return self.pipeline.run(
                source=source,
                search=search,
                listing_html=listing_html,
                detail_pages=detail_pages,
            )
