
from typing import Mapping

from backend.app.database import SessionLocal
from backend.app.repositories.search_repository import SearchRepository
from backend.app.schemas.job import (
    JobSearchRequest,
    JobSearchResultsResponse,
    JobSource,
)
from backend.app.services.job_pipeline import JobExtractionPipeline


class JobSearchExecutor:
    """
    Execute a search and persist its results.

    The extraction pipeline currently receives supplied HTML.
    Live browser fetching will be integrated separately.
    """

    def __init__(self):
        self.repository = SearchRepository()
        self.pipeline = JobExtractionPipeline()

    def run_from_html(
        self,
        search_id: str,
        source: JobSource,
        listing_html: str,
        detail_pages: Mapping[str, str],
    ) -> JobSearchResultsResponse:

        # Commit the running status before extraction.
        with SessionLocal.begin() as db:
            task = self.repository.start(
                db,
                search_id,
            )

            search_request = JobSearchRequest.model_validate(
                task.request_payload
            )

            if task.source != source.value:
                raise ValueError("Search source mismatch")

        try:
            result = self.pipeline.run(
                source=source,
                search=search_request,
                listing_html=listing_html,
                detail_pages=detail_pages,
            )

            # Save jobs, associations and failures atomically.
            with SessionLocal.begin() as db:
                self.repository.complete(
                    db,
                    search_id,
                    result,
                )

                response = self.repository.get_results(
                    db,
                    search_id,
                )

                if response is None:
                    raise RuntimeError(
                        "Persisted search results unavailable"
                    )

            return response

        except Exception as exc:
            # The previous transaction is rolled back if
            # saving results failed.
            with SessionLocal.begin() as db:
                self.repository.fail(
                    db,
                    search_id,
                    f"{type(exc).__name__}: {exc}",
                )

            raise
