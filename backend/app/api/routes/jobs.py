
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from backend.app.models.job import Job
from backend.app.models.search import SearchTaskRecord, SearchTaskJob
from backend.app.schemas.job import AssistedJobInput, JobListing
from backend.app.services.job_deduplication import extract_job_id, normalize_job_url
from backend.app.repositories.search_repository import utc_now

from backend.app.database import SessionLocal, get_db
from backend.app.repositories.search_event_repository import SearchEventRepository
from backend.app.repositories.search_repository import SearchRepository
from backend.app.repositories.job_repository import JobRepository
from backend.app.schemas.job import (
    JobSearchRequest,
    JobSearchResponse,
    JobSearchResultsResponse,
    JobSource,
    PersistedJobResponse,
)
from backend.app.services.task_manager import SearchTask
from backend.app.services.search_event_stream import stream_search_events


router = APIRouter(prefix="/jobs", tags=["Jobs"])

repository = SearchRepository()


def parse_search_id(search_id: str) -> UUID:
    try:
        return UUID(search_id)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail="Search task not found",
        )


@router.post(
    "/search",
    response_model=JobSearchResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_job_search(
    request: JobSearchRequest,
    db: Session = Depends(get_db),
):
    task = repository.create(
        db,
        request,
        source=JobSource(request.source),
    )

    SearchEventRepository.publish(db, task.search_id, "search_queued", {
        "search_id": str(task.search_id), "status": "pending", "source": task.source,
    })
    db.commit()
    db.refresh(task)

    return JobSearchResponse(
        search_id=str(task.search_id),
        status=task.status,
        message="Search task created. Worker execution pending.",
    )


@router.get(
    "/search/{search_id}",
    response_model=SearchTask,
)
def get_job_search(
    search_id: str,
    db: Session = Depends(get_db),
):
    task = repository.get(
        db,
        parse_search_id(search_id),
    )

    if task is None:
        raise HTTPException(
            status_code=404,
            detail="Search task not found",
        )

    return SearchTask(
        search_id=str(task.search_id),
        status=task.status,
        request=JobSearchRequest.model_validate(
            task.request_payload
        ),
        created_at=task.created_at,
        updated_at=task.updated_at,
        error=task.error,
    )


@router.get(
    "/search/{search_id}/results",
    response_model=JobSearchResultsResponse,
)
def get_job_search_results(
    search_id: str,
    db: Session = Depends(get_db),
):
    results = repository.get_results(
        db,
        parse_search_id(search_id),
    )

    if results is None:
        raise HTTPException(
            status_code=404,
            detail="Search task not found",
        )

    return results


def parse_event_cursor(value: str | None) -> int:
    if value is None:
        return 0
    # PostgreSQL INTEGER sequences; bound length before int conversion as well.
    if not value.isascii() or not value.isdecimal() or len(value) > 10:
        raise HTTPException(422, "Event cursor must be a nonnegative integer")
    cursor = int(value)
    if cursor > 2_147_483_647:
        raise HTTPException(422, "Event cursor exceeds the sequence range")
    return cursor


@router.get("/search/{search_id}/events")
def get_search_events(
    search_id: UUID,
    request: Request,
    after: str | None = Query(default=None),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
):
    """Replay after the cursor; Last-Event-ID takes precedence over `after`."""
    # Validate both supplied values, including the overridden cursor.
    query_cursor = parse_event_cursor(after)
    header_cursor = parse_event_cursor(last_event_id)
    cursor = header_cursor if last_event_id is not None else query_cursor
    # A synchronous route runs in FastAPI's thread pool. Do not use a yielded
    # request session here: it could otherwise survive for the entire stream.
    with SessionLocal() as db:
        if repository.get(db, search_id) is None:
            raise HTTPException(404, "Search task not found")
    return StreamingResponse(
        stream_search_events(request, search_id, cursor),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{job_id}", response_model=PersistedJobResponse)
def get_job(job_id: UUID, db: Session = Depends(get_db)):
    job = JobRepository.get_by_id(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return PersistedJobResponse.model_validate(job, from_attributes=True)


@router.post("/search/{search_id}/assisted-jobs", response_model=PersistedJobResponse)
def save_assisted_job(search_id: UUID, request: AssistedJobInput, db: Session = Depends(get_db)):
    """Save only user-supplied fields. Never fetch a restricted website."""
    task = db.scalar(select(SearchTaskRecord).where(SearchTaskRecord.search_id == search_id).with_for_update())
    if task is None:
        raise HTTPException(404, "Search task not found")
    if task.source not in ("linkedin", "wellfound"):
        raise HTTPException(422, "Manual entry is available for assisted sources only")
    if task.status not in ("completed", "failed"):
        raise HTTPException(409, "Wait for the worker to open your browser before saving")
    source = JobSource(task.source)
    try:
        job_id = extract_job_id(source, request.job_url)
    except ValueError:
        job_id = None
    if job_id is None:
        raise HTTPException(422, "Use an original HTTPS job listing URL from the selected source")
    listing = JobListing(source=source, **request.model_dump())
    existing = db.scalar(select(Job).join(SearchTaskJob).where(
        SearchTaskJob.search_id == search_id, Job.source == task.source,
        Job.job_url == normalize_job_url(source, request.job_url)))
    if existing is None and task.total_extracted >= task.request_payload.get("max_results", 50):
        raise HTTPException(409, "This search has reached its maximum results")
    saved = JobRepository.upsert(db, listing)
    db.execute(insert(SearchTaskJob).values(search_id=search_id, job_id=saved.id).on_conflict_do_nothing())
    db.flush()
    count = db.scalar(select(func.count()).select_from(SearchTaskJob).where(SearchTaskJob.search_id == search_id))
    task.total_extracted = count
    task.total_discovered = count
    task.updated_at = utc_now()
    db.commit()
    db.refresh(saved)
    return PersistedJobResponse.model_validate(saved, from_attributes=True)
