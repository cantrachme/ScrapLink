
from uuid import uuid4

from fastapi import APIRouter, status

from backend.app.schemas.job import (
    JobSearchRequest,
    JobSearchResponse,
)

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.post(
    "/search",
    response_model=JobSearchResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_job_search(request: JobSearchRequest):
    search_id = str(uuid4())

    return JobSearchResponse(
        search_id=search_id,
        status="accepted",
        message="Search request validated. Worker integration pending.",
    )
