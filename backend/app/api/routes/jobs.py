
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.repositories.search_repository import SearchRepository
from backend.app.schemas.job import (
    JobSearchRequest,
    JobSearchResponse,
    JobSearchResultsResponse,
    JobSource,
)
from backend.app.services.task_manager import SearchTask


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
