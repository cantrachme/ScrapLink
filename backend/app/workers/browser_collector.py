import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from scrapling.fetchers import DynamicSession
from scrapling.parser import Selector

from backend.app.schemas.job import JobSearchRequest, JobSource
from backend.app.schemas.search_event import JOB_FAILURE_MESSAGE, ProgressCallback
from backend.app.services.job_deduplication import job_identity
from backend.app.services.job_pipeline import (
    ExtractionFailure,
    JobExtractionPipeline,
    PipelineResult,
)
from backend.app.sources.linkedin.search import build_linkedin_search_url
from backend.app.sources.pagination import build_paginated_search_url, paginate_search_url
from backend.app.sources.search_router import build_source_search_url
from backend.app.sources.wellfound.search import build_wellfound_search_url


logger = logging.getLogger(__name__)

ListingURLBuilder = Callable[[JobSource, JobSearchRequest], str]
DetailURLBuilder = Callable[[JobSource, str], str]


class BrowserCollector:
    """Collect public listings and details in one browser session.

    Custom source listing URLs retain their parameters during pagination.
    Custom off-source listing builders retain the legacy single-page behavior
    for controlled fixtures; source pagination is never applied to those URLs.
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
        max_pages: int = 10,
    ):
        if type(max_pages) is not int or max_pages < 1:
            raise ValueError("max_pages must be a positive integer")
        self.listing_url_builder = listing_url_builder
        self.detail_url_builder = detail_url_builder or (lambda source, job_url: job_url)
        self.session_factory = session_factory
        self.headless = headless
        self.real_chrome = real_chrome
        self.wait_ms = wait_ms
        self.max_pages = max_pages
        self.pipeline = JobExtractionPipeline()

    @staticmethod
    def _is_allowed_job_url(source: JobSource, job_url: str) -> bool:
        parsed = urlsplit(job_url)
        allowed_hosts = {
            JobSource.LINKEDIN: {"linkedin.com", "www.linkedin.com"},
            JobSource.WELLFOUND: {"wellfound.com", "www.wellfound.com"},
        }
        return (
            parsed.scheme == "https"
            and parsed.hostname in allowed_hosts.get(source, set())
            and parsed.username is None
            and parsed.password is None
            and parsed.port in (None, 443)
        )

    def _fetch_html(self, session: Any, url: str) -> str:
        response = session.fetch(
            url, google_search=False, timeout=30000, wait=self.wait_ms,
        )
        if response.status >= 300:
            raise RuntimeError(f"Browser received HTTP {response.status} for {url}")
        html = response.body.decode(response.encoding or "utf-8", errors="replace")

        # Recognize explicit access gates, including HTTP-200 login/challenge
        # pages. Never attempt authentication, retries, or challenge bypasses.
        final_path = urlsplit(str(getattr(response, "url", url))).path.lower()
        page = Selector(content=html)
        title = str(page.css("title::text").get() or "").strip().casefold()
        if (
            final_path.startswith(("/login", "/checkpoint", "/auth/", "/users/login"))
            or title in {
                "security verification | linkedin", "linkedin login, sign in | linkedin",
                "just a moment...", "access denied", "sign in - wellfound",
            }
            or page.css('form[action*="/checkpoint/"]')
        ):
            raise RuntimeError(f"Authentication or access challenge encountered for {url}")
        return html

    def __call__(self, source: JobSource, search: JobSearchRequest) -> PipelineResult:
        return self.collect_with_progress(source, search)

    def collect_with_progress(
        self, source: JobSource, search: JobSearchRequest,
        progress: ProgressCallback | None = None,
    ) -> PipelineResult:
        """Callbacks are per invocation, synchronous, and may raise to abort.

        Callers must close their DB transactions before entering this method.
        Callback failures are deliberately outside fetch/extraction handlers.
        """
        if source not in (JobSource.LINKEDIN, JobSource.WELLFOUND):
            raise ValueError(f"Unsupported job source: {source}")
        if search.source != source.value:
            raise ValueError("Search request source must match collector source")
        listing_url = self.listing_url_builder(source, search)
        built_in = self.listing_url_builder in (
            build_source_search_url, build_linkedin_search_url, build_wellfound_search_url,
        )
        hostname = urlsplit(listing_url).hostname or ""
        source_domain = f"{source.value}.com"
        source_url = hostname == source_domain or hostname.endswith(f".{source_domain}")
        if built_in or source_url:
            # Validate even page one, so /jobs application URLs cannot silently
            # masquerade as supported Wellfound public role searches.
            paginate_search_url(source, listing_url, 1)
            page_limit = self.max_pages
        else:
            page_limit = 1
            logger.info("Using a single page for custom listing URL: %s", listing_url)

        reference = datetime.now(timezone.utc)
        result = PipelineResult(source=source)
        seen: set[tuple[JobSource, str]] = set()
        with self.session_factory(
            headless=self.headless, real_chrome=self.real_chrome, network_idle=False,
        ) as session:
            for page_number in range(1, page_limit + 1):
                if page_number == 1:
                    page_url = listing_url
                elif built_in:
                    page_url = build_paginated_search_url(source, search, page_number)
                else:
                    page_url = paginate_search_url(source, listing_url, page_number)
                listing_html = self._fetch_html(session, page_url)
                new_urls = []
                for job_url in self.pipeline.discover_urls(source, search, listing_html):
                    key = job_identity(source, job_url)
                    if key not in seen:
                        seen.add(key)
                        new_urls.append(job_url)
                result.discovered_urls.extend(new_urls)
                if progress is not None:
                    progress("page_discovered", {
                        "page_number": page_number,
                        "new_jobs_discovered": len(new_urls),
                        "total_discovered": result.total_discovered,
                    })
                if not new_urls:
                    break

                for job_url in new_urls:
                    previous_extracted = result.total_extracted
                    previous_failed = result.total_failed
                    if not self._is_allowed_job_url(source, job_url):
                        result.failures.append(ExtractionFailure(
                            job_url=job_url, error="Unexpected source job URL",
                        ))
                    else:
                        try:
                            fetch_url = self.detail_url_builder(source, job_url)
                            html = self._fetch_html(session, fetch_url)
                        except Exception as exc:
                            logger.exception("Failed to fetch job: %s", job_url)
                            result.failures.append(ExtractionFailure(
                                job_url=job_url, error=f"{type(exc).__name__}: {exc}",
                            ))
                        else:
                            self.pipeline.add_detail(result, search, job_url, html, now=reference)
                    if progress is not None:
                        if result.total_extracted > previous_extracted:
                            job = result.jobs[-1]
                            progress("job_extracted", {
                                "job_url": job.job_url, "title": job.title,
                                "company": job.company,
                                "total_extracted": result.total_extracted,
                            })
                        elif result.total_failed > previous_failed:
                            progress("job_failed", {
                                "job_url": job_url, "error": JOB_FAILURE_MESSAGE,
                                "total_failed": result.total_failed,
                            })
                    if result.total_extracted >= search.max_results:
                        return result
        return result
