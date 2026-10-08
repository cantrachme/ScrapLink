
import logging
import time

from collections.abc import Callable
from uuid import UUID

from backend.app.database import SessionLocal
from backend.app.repositories.search_event_repository import SearchEventRepository
from backend.app.schemas.search_event import SEARCH_FAILURE_MESSAGE
from backend.app.repositories.search_repository import (
    SearchRepository,
)
from backend.app.schemas.job import (
    JobSearchRequest,
    JobSource,
)
from backend.app.services.job_pipeline import PipelineResult


logger = logging.getLogger(__name__)

Collector = Callable[
    [JobSource, JobSearchRequest],
    PipelineResult,
]


class JobQueueWorker:
    """
    PostgreSQL-backed job search worker.

    The collector is injected so browser execution
    remains independent of queue management.
    """

    def __init__(self, collector: Collector):
        self.collector = collector
        self.repository = SearchRepository()
        self.events = SearchEventRepository()

    def run_once(
        self,
        search_id: UUID | None = None,
    ) -> bool:
        """
        Claim and process one task.

        Returns False when no eligible task exists.
        """

        with SessionLocal.begin() as db:
            task = self.repository.claim_next_pending(
                db,
                search_id=search_id,
            )

            if task is None:
                return False

            claimed_id = task.search_id
            source_value = task.source
            request_payload = dict(task.request_payload)
            self.events.publish(db, claimed_id, "search_started", {
                "search_id": str(claimed_id), "status": "running",
                "source": source_value or request_payload["source"],
            })

        # The claiming transaction has now committed.
        # Browser work must happen outside DB transactions.

        try:
            request = JobSearchRequest.model_validate(
                request_payload
            )

            source = JobSource(
                source_value or request.source
            )

            logger.info(
                "Processing search %s (%s)",
                claimed_id,
                source.value,
            )

            def publish_progress(event_type: str, payload: dict) -> None:
                if event_type not in {"page_discovered", "job_extracted", "job_failed"}:
                    raise ValueError("Collector emitted a non-progress event")
                with SessionLocal.begin() as db:
                    self.events.publish(db, claimed_id, event_type, payload)

            collect_with_progress = getattr(self.collector, "collect_with_progress", None)
            if callable(collect_with_progress):
                result = collect_with_progress(source, request, publish_progress)
            else:
                result = self.collector(source, request)

            if result.source != source:
                raise ValueError(
                    "Collector returned an unexpected source"
                )

            with SessionLocal.begin() as db:
                self.repository.complete(
                    db,
                    claimed_id,
                    result,
                )
                self.events.publish(db, claimed_id, "search_completed", {
                    "search_id": str(claimed_id), "status": "completed",
                    "total_discovered": result.total_discovered,
                    "total_extracted": result.total_extracted,
                    "total_failed": result.total_failed,
                })

            logger.info(
                "Completed search %s",
                claimed_id,
            )

        except Exception as exc:
            logger.exception(
                "Search %s failed",
                claimed_id,
            )

            with SessionLocal.begin() as db:
                self.repository.fail(
                    db,
                    claimed_id,
                    f"{type(exc).__name__}: {exc}",
                )
                self.events.publish(db, claimed_id, "search_failed", {
                    "search_id": str(claimed_id), "status": "failed",
                    "error": SEARCH_FAILURE_MESSAGE,
                })

        return True

    def run_forever(
        self,
        poll_interval_seconds: float = 2.0,
    ) -> None:
        """Continuously process available searches."""

        if poll_interval_seconds <= 0:
            raise ValueError(
                "Polling interval must be positive"
            )

        logger.info("ScrapLink queue worker started")

        try:
            while True:
                processed = self.run_once()

                if not processed:
                    time.sleep(poll_interval_seconds)

        except KeyboardInterrupt:
            logger.info("ScrapLink queue worker stopped")
