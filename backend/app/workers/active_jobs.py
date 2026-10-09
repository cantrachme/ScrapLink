"""Multi-source orchestration using the existing queue, row locks and SSE log."""
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from backend.app.database import SessionLocal
from backend.app.models.search import SearchTaskJob, ExtractionFailureRecord
from backend.app.repositories.job_repository import JobRepository
from backend.app.repositories.search_repository import utc_now
from backend.app.schemas.job import JobListing, JobSource, JobStatus
from backend.app.services.active_job_details import matches_active_posting_window

SOURCES = (JobSource.LINKEDIN, JobSource.WELLFOUND)
SOURCE_MESSAGES = {
    "authorization_required": "Automated discovery is not authorized. Chrome is open for manual browsing; save permitted listing details below.",
    "access_blocked": "Authentication, CAPTCHA, or a platform restriction stopped this source. Use manual browsing and permitted entry; no bypass was attempted.",
    "failed": "This source could not be inspected. Saved jobs are retained; manual entry remains available.",
}


class SourceUnavailable(RuntimeError):
    def __init__(self, status):
        self.status = status
        super().__init__(SOURCE_MESSAGES[status])


class PersistenceFailure(RuntimeError):
    """A callback failure must abort the task, not be treated as a source error."""


def run_active_jobs(worker, search_id, request):
    def locked(db):
        task = worker.repository._get_locked(db, search_id)
        if task.status != "running":
            raise PersistenceFailure("Search execution ownership was lost")
        task.updated_at = utc_now()
        return task

    def source_status(source, status):
        worker.check_shutdown()
        with SessionLocal.begin() as db:
            task = locked(db)
            if status in SOURCE_MESSAGES:
                db.add(ExtractionFailureRecord(search_id=search_id, source=source.value,
                                               error=SOURCE_MESSAGES[status]))
                task.total_failed += 1
            worker.events.publish(db, search_id, "source_status", {"source": source.value, "status": status})

    for index, source in enumerate(SOURCES):
        worker.check_shutdown()
        with SessionLocal() as db:
            remaining = request.max_results - worker.repository.get(db, search_id).total_extracted
        if remaining <= 0:
            source_status(source, "limit_reached")
            continue
        # Give both sources a chance before spending the global budget.
        budget = max(1, remaining // 2) if index == 0 else remaining
        source_request = request.model_copy(update={"source": source.value, "max_results": budget})
        source_status(source, "collecting")
        seen_discovered = 0

        def progress(event_type, payload):
            nonlocal seen_discovered
            worker.check_shutdown()
            try:
                with SessionLocal.begin() as db:
                    task = locked(db)
                    if event_type == "job_collected":
                        job = JobListing.model_validate(payload["job"])
                        if job.source != source:
                            raise ValueError("Collector source mismatch")
                        if job.status == JobStatus.CLOSED or not matches_active_posting_window(job):
                            return
                        if task.total_extracted >= request.max_results:
                            return
                        saved = JobRepository.upsert_active(db, job)
                        db.execute(insert(SearchTaskJob).values(search_id=search_id, job_id=saved.id)
                                   .on_conflict_do_nothing())
                        task.total_extracted = db.scalar(select(func.count()).select_from(SearchTaskJob)
                            .where(SearchTaskJob.search_id == search_id))
                        task.total_discovered = max(task.total_discovered, task.total_extracted)
                        worker.events.publish(db, search_id, "job_saved", {
                            "job_id": str(saved.id), "source": source.value,
                            "total_extracted": task.total_extracted,
                        })
                    elif event_type == "page_discovered":
                        current = payload["total_discovered"]
                        task.total_discovered += max(0, current - seen_discovered)
                        seen_discovered = current
                        worker.events.publish(db, search_id, event_type,
                            {**payload, "total_discovered": task.total_discovered})
                    elif event_type == "job_failed":
                        task.total_failed += 1
                        db.add(ExtractionFailureRecord(search_id=search_id, source=source.value,
                            job_url=payload["job_url"], error="Job detail fetching or extraction failed"))
                        worker.events.publish(db, search_id, event_type,
                            {**payload, "total_failed": task.total_failed})
                    elif event_type == "browser_action":
                        worker.events.publish(db, search_id, event_type, payload)
                    else:
                        raise ValueError("Unexpected Active Jobs collector event")
            except Exception as exc:
                raise PersistenceFailure("Could not persist discovery progress") from exc

        try:
            collect = getattr(worker.collector, "collect_with_progress", None)
            if collect is None:
                raise RuntimeError("Active Jobs requires a streaming collector")
            result = collect(source, source_request, progress)
            if result.source != source:
                raise ValueError("Collector source mismatch")
        except PersistenceFailure:
            raise
        except Exception as exc:
            from backend.app.workers.queue_worker import WorkerShutdown
            if isinstance(exc, WorkerShutdown):
                raise
            source_status(source, exc.status if isinstance(exc, SourceUnavailable) else "failed")
        else:
            source_status(source, "completed")

    worker.check_shutdown()
    with SessionLocal.begin() as db:
        task = locked(db)
        task.status = "completed"
        task.finished_at = utc_now()
        worker.events.publish(db, search_id, "search_completed", {
            "search_id": str(search_id), "status": "completed",
            "total_discovered": task.total_discovered,
            "total_extracted": task.total_extracted, "total_failed": task.total_failed,
        })
