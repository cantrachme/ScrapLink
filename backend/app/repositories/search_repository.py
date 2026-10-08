
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.app.models.job import Job
from backend.app.models.search import (
    SearchTaskRecord,
    SearchTaskJob,
    ExtractionFailureRecord,
)
from backend.app.repositories.job_repository import JobRepository
from backend.app.schemas.job import (
    JobListing,
    JobSearchRequest,
    JobSearchResultsResponse,
    JobExtractionFailure,
    JobSource,
)
from backend.app.services.job_pipeline import PipelineResult


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SearchRepository:
    """Persistent storage for search tasks and their results."""


    @staticmethod
    def claim_next_pending(
        db: Session,
        search_id: UUID | None = None,
    ) -> SearchTaskRecord | None:
        """
        Atomically claim one pending search.

        SKIP LOCKED prevents multiple workers from
        claiming the same task concurrently.
        """

        statement = (
            select(SearchTaskRecord)
            .where(SearchTaskRecord.status == "pending")
            .order_by(
                SearchTaskRecord.created_at,
                SearchTaskRecord.search_id,
            )
            .with_for_update(skip_locked=True)
            .limit(1)
        )

        if search_id is not None:
            statement = statement.where(
                SearchTaskRecord.search_id == search_id
            )

        task = db.scalar(statement)

        if task is None:
            return None

        task.status = "running"
        task.started_at = utc_now()
        task.updated_at = utc_now()

        db.flush()
        return task


    @staticmethod
    def create(
        db: Session,
        request: JobSearchRequest,
        source: JobSource | None = None,
    ) -> SearchTaskRecord:
        task = SearchTaskRecord(
            search_id=uuid4(),
            source=source.value if source else None,
            request_payload=request.model_dump(mode="json"),
            status="pending",
        )

        db.add(task)
        db.flush()
        return task

    @staticmethod
    def get(
        db: Session,
        search_id: str | UUID,
    ) -> SearchTaskRecord | None:
        return db.get(SearchTaskRecord, UUID(str(search_id)))

    @staticmethod
    def _get_locked(
        db: Session,
        search_id: str | UUID,
    ) -> SearchTaskRecord:
        task = db.scalar(
            select(SearchTaskRecord)
            .where(
                SearchTaskRecord.search_id == UUID(str(search_id))
            )
            .with_for_update()
        )

        if task is None:
            raise KeyError("Search task not found")

        return task

    @classmethod
    def start(
        cls,
        db: Session,
        search_id: str | UUID,
    ) -> SearchTaskRecord:
        task = cls._get_locked(db, search_id)

        if task.status != "pending":
            raise ValueError("Only pending tasks can be started")

        task.status = "running"
        task.started_at = utc_now()
        task.updated_at = utc_now()

        db.flush()
        return task

    @classmethod
    def complete(
        cls,
        db: Session,
        search_id: str | UUID,
        result: PipelineResult,
    ) -> SearchTaskRecord:
        task = cls._get_locked(db, search_id)

        if task.status != "running":
            raise ValueError("Search task is not running")

        if task.source and task.source != result.source.value:
            raise ValueError("Search source mismatch")

        # Save each extracted job and link it to this search.
        for listing in result.jobs:
            if listing.source != result.source:
                raise ValueError("Job source mismatch")

            saved_job = JobRepository.upsert(db, listing)

            stmt = insert(SearchTaskJob).values(
                search_id=task.search_id,
                job_id=saved_job.id,
            ).on_conflict_do_nothing(
                index_elements=["search_id", "job_id"]
            )

            db.execute(stmt)

        # Save extraction failures independently.
        for failure in result.failures:
            db.add(
                ExtractionFailureRecord(
                    search_id=task.search_id,
                    source=result.source.value,
                    job_url=failure.job_url,
                    error=failure.error,
                )
            )

        task.source = result.source.value
        task.status = "completed"

        task.total_discovered = result.total_discovered
        task.total_extracted = result.total_extracted
        task.total_failed = result.total_failed

        task.finished_at = utc_now()
        task.updated_at = utc_now()
        task.error = None

        db.flush()
        return task

    @classmethod
    def fail(
        cls,
        db: Session,
        search_id: str | UUID,
        error: str,
    ) -> SearchTaskRecord:
        task = cls._get_locked(db, search_id)

        if task.status != "running":
            raise ValueError("Only running tasks can fail")

        task.status = "failed"
        task.error = error
        task.finished_at = utc_now()
        task.updated_at = utc_now()

        db.flush()
        return task

    @classmethod
    def get_results(
        cls,
        db: Session,
        search_id: str | UUID,
    ) -> JobSearchResultsResponse | None:
        task = cls.get(db, search_id)

        if task is None:
            return None

        stored_jobs = db.scalars(
            select(Job)
            .join(
                SearchTaskJob,
                SearchTaskJob.job_id == Job.id,
            )
            .where(SearchTaskJob.search_id == task.search_id)
            .order_by(
                SearchTaskJob.discovered_at,
                SearchTaskJob.job_id,
            )
        ).all()

        stored_failures = db.scalars(
            select(ExtractionFailureRecord)
            .where(
                ExtractionFailureRecord.search_id == task.search_id
            )
            .order_by(
                ExtractionFailureRecord.created_at,
                ExtractionFailureRecord.id,
            )
        ).all()

        jobs = [
            JobListing.model_validate(job, from_attributes=True)
            for job in stored_jobs
        ]

        failures = [
            JobExtractionFailure(
                job_url=failure.job_url or "",
                error=failure.error,
            )
            for failure in stored_failures
        ]

        # Reconstruct discovered URLs from stored records.
        # The original discovery order is not preserved yet.
        discovered_urls = list(
            dict.fromkeys(
                [job.job_url for job in jobs]
                + [failure.job_url for failure in failures]
            )
        )

        return JobSearchResultsResponse(
            search_id=str(task.search_id),
            status=task.status,
            source=JobSource(task.source) if task.source else None,
            discovered_urls=discovered_urls,
            jobs=jobs,
            failures=failures,
            total_discovered=task.total_discovered,
            total_extracted=task.total_extracted,
            total_failed=task.total_failed,
        )
