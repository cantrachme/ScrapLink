
from typing import Mapping

from backend.app.schemas.job import (
    JobExtractionFailure,
    JobSearchResultsResponse,
    JobSource,
)
from backend.app.services.job_pipeline import (
    JobExtractionPipeline,
)
from backend.app.services.task_manager import (
    SearchTaskManager,
    TaskStatus,
)


class JobSearchExecutor:
    def __init__(self, manager: SearchTaskManager):
        self.manager = manager
        self.pipeline = JobExtractionPipeline()

    def run_from_html(
        self,
        search_id: str,
        source: JobSource,
        listing_html: str,
        detail_pages: Mapping[str, str],
    ) -> JobSearchResultsResponse:
        """Execute a search from supplied HTML fixtures."""

        task = self.manager.start_task(search_id)

        try:
            output = self.pipeline.run(
                source=source,
                search=task.request,
                listing_html=listing_html,
                detail_pages=detail_pages,
            )

            results = JobSearchResultsResponse(
                search_id=search_id,
                status=TaskStatus.COMPLETED.value,
                source=source,
                discovered_urls=output.discovered_urls,
                jobs=output.jobs,
                failures=[
                    JobExtractionFailure(
                        job_url=failure.job_url,
                        error=failure.error,
                    )
                    for failure in output.failures
                ],
                total_discovered=output.total_discovered,
                total_extracted=output.total_extracted,
                total_failed=output.total_failed,
            )

            self.manager.complete_task(
                search_id,
                results,
            )

            return results

        except Exception as exc:
            self.manager.update_status(
                search_id,
                TaskStatus.FAILED,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise
