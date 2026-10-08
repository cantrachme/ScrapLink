import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping

from scrapling.parser import Selector

from backend.app.schemas.job import JobListing, JobSearchRequest, JobSource
from backend.app.services.job_deduplication import job_identity
from backend.app.services.job_filters import matches_posting_window
from backend.app.sources.base import BaseJobSourceAdapter
from backend.app.sources.linkedin.adapter import LinkedInJobAdapter
from backend.app.sources.wellfound.adapter import WellfoundJobAdapter


logger = logging.getLogger(__name__)


@dataclass
class ExtractionFailure:
    job_url: str
    error: str


@dataclass
class PipelineResult:
    source: JobSource
    discovered_urls: list[str] = field(default_factory=list)
    jobs: list[JobListing] = field(default_factory=list)
    failures: list[ExtractionFailure] = field(default_factory=list)

    @property
    def total_discovered(self) -> int:
        return len(self.discovered_urls)

    @property
    def total_extracted(self) -> int:
        return len(self.jobs)

    @property
    def total_failed(self) -> int:
        return len(self.failures)


class JobExtractionPipeline:
    """Discover independently of detail extraction and posting-date validation."""

    def __init__(self):
        self.adapters: dict[JobSource, BaseJobSourceAdapter] = {
            JobSource.LINKEDIN: LinkedInJobAdapter(),
            JobSource.WELLFOUND: WellfoundJobAdapter(),
        }

    def _adapter(self, source: JobSource) -> BaseJobSourceAdapter:
        adapter = self.adapters.get(source)
        if adapter is None:
            raise ValueError(f"Unsupported job source: {source}")
        return adapter

    def discover_urls(
        self,
        source: JobSource,
        search: JobSearchRequest,
        listing_html: str,
    ) -> list[str]:
        return self._adapter(source).discover_job_urls(
            Selector(content=listing_html), search,
        )

    def add_detail(
        self,
        result: PipelineResult,
        search: JobSearchRequest,
        job_url: str,
        html: str | None,
        *,
        now: datetime,
    ) -> None:
        """Extract once; append a qualifying job or a genuine extraction failure."""
        adapter = self._adapter(result.source)
        if not html:
            result.failures.append(ExtractionFailure(
                job_url=job_url, error="Job detail HTML unavailable",
            ))
            return
        try:
            job = adapter.extract_job_details(Selector(content=html), job_url)
        except Exception as exc:
            result.failures.append(ExtractionFailure(
                job_url=job_url, error=f"{type(exc).__name__}: {exc}",
            ))
            return

        if matches_posting_window(job, search.date_posted, now):
            result.jobs.append(job)
        else:
            logger.info(
                "Excluded job %s from posting window %s (posted_at=%s, posted_date=%s)",
                job_url, search.date_posted, job.posted_at, job.posted_date,
            )

    def run(
        self,
        source: JobSource,
        search: JobSearchRequest,
        listing_html: str,
        detail_pages: Mapping[str, str],
        *,
        now: datetime | None = None,
    ) -> PipelineResult:
        reference = now or datetime.now(timezone.utc)
        job_urls = self.discover_urls(source, search, listing_html)
        result = PipelineResult(source=source, discovered_urls=job_urls)
        # Supplied fixture pages may be keyed by a tracking or slug variant.
        pages_by_identity: dict[tuple[JobSource, str], str] = {}
        for url, html in detail_pages.items():
            pages_by_identity.setdefault(job_identity(source, url), html)

        for job_url in job_urls:
            if result.total_extracted >= search.max_results:
                break
            self.add_detail(
                result, search, job_url,
                pages_by_identity.get(job_identity(source, job_url)),
                now=reference,
            )
        return result
