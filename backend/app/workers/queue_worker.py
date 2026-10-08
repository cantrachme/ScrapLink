
import logging
import time

from collections.abc import Callable
from uuid import UUID

from backend.app.database import SessionLocal
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
