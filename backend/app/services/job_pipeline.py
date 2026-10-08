
from dataclasses import dataclass, field
from typing import Mapping

from scrapling.parser import Selector

from backend.app.schemas.job import (
    JobListing,
    JobSearchRequest,
    JobSource,
)
from backend.app.sources.base import BaseJobSourceAdapter
from backend.app.sources.linkedin.adapter import LinkedInJobAdapter
from backend.app.sources.wellfound.adapter import WellfoundJobAdapter


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
    """Process job listing and detail HTML through source adapters."""

    def __init__(self):
        self.adapters: dict[JobSource, BaseJobSourceAdapter] = {
            JobSource.LINKEDIN: LinkedInJobAdapter(),
            JobSource.WELLFOUND: WellfoundJobAdapter(),
        }

    def run(
        self,
        source: JobSource,
        search: JobSearchRequest,
        listing_html: str,
        detail_pages: Mapping[str, str],
    ) -> PipelineResult:

        adapter = self.adapters.get(source)

        if adapter is None:
            raise ValueError(f"Unsupported job source: {source}")

        listing_page = Selector(content=listing_html)

        job_urls = adapter.discover_job_urls(
            listing_page,
            search,
        )

        result = PipelineResult(
            source=source,
            discovered_urls=job_urls,
        )

        for job_url in job_urls:
            html = detail_pages.get(job_url)

            if not html:
                result.failures.append(
                    ExtractionFailure(
                        job_url=job_url,
                        error="Job detail HTML unavailable",
                    )
                )
                continue

            try:
                detail_page = Selector(content=html)

                job = adapter.extract_job_details(
                    detail_page,
                    job_url,
                )

                result.jobs.append(job)

            except Exception as exc:
                result.failures.append(
                    ExtractionFailure(
                        job_url=job_url,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                )

        return result
