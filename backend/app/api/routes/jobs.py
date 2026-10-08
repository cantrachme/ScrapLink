
from fastapi import APIRouter, HTTPException, status

from backend.app.schemas.job import (
    JobSearchRequest,
    JobSearchResponse,
)
from backend.app.services.task_manager import (
    SearchTask,
    task_manager,
)

from backend.app.schemas.job import JobSearchResultsResponse

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.post(
    "/search",
    response_model=JobSearchResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_job_search(request: JobSearchRequest):
    task = task_manager.create_task(request)

    return JobSearchResponse(
        search_id=task.search_id,
        status=task.status.value,
        message="Search task created. Worker execution pending.",
    )


@router.get(
    "/search/{search_id}",
    response_model=SearchTask,
)
async def get_job_search(search_id: str):
    task = task_manager.get_task(search_id)

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Search task not found",
        )

    return task


@router.get(
    "/search/{search_id}/results",
    response_model=JobSearchResultsResponse,
)
async def get_job_search_results(search_id: str):
    results = task_manager.get_results(search_id)

    if results is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Search task not found",
        )

    return results
