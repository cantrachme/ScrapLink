
from datetime import datetime, timezone
from enum import Enum
from threading import Lock
from uuid import uuid4

from pydantic import BaseModel, Field

from backend.app.schemas.job import JobSearchRequest

from backend.app.schemas.job import JobSearchResultsResponse


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SearchTask(BaseModel):
    search_id: str
    status: TaskStatus = TaskStatus.PENDING
    request: JobSearchRequest
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    error: str | None = None


class SearchTaskManager:
    def __init__(self):
        self._tasks: dict[str, SearchTask] = {}
        self._lock = Lock()
        self._results: dict[str, JobSearchResultsResponse] = {}

    def create_task(self, request: JobSearchRequest) -> SearchTask:
        task = SearchTask(
            search_id=str(uuid4()),
            request=request,
        )

        with self._lock:
            self._tasks[task.search_id] = task

        return task.model_copy(deep=True)

    def get_task(self, search_id: str) -> SearchTask | None:
        with self._lock:
            task = self._tasks.get(search_id)
            return task.model_copy(deep=True) if task else None

    def update_status(
        self,
        search_id: str,
        status: TaskStatus,
        error: str | None = None,
    ) -> SearchTask | None:
        with self._lock:
            task = self._tasks.get(search_id)

            if task is None:
                return None

            task.status = status
            task.error = error
            task.updated_at = datetime.now(timezone.utc)

            return task.model_copy(deep=True)


    def start_task(self, search_id: str) -> SearchTask:
        with self._lock:
            task = self._tasks.get(search_id)

            if task is None:
                raise KeyError("Search task not found")

            if task.status != TaskStatus.PENDING:
                raise ValueError(
                    "Only pending searches can be started"
                )

            task.status = TaskStatus.RUNNING
            task.updated_at = datetime.now(timezone.utc)

            return task.model_copy(deep=True)

    def complete_task(
        self,
        search_id: str,
        results: JobSearchResultsResponse,
    ) -> SearchTask:
        with self._lock:
            task = self._tasks.get(search_id)

            if task is None:
                raise KeyError("Search task not found")

            if task.status != TaskStatus.RUNNING:
                raise ValueError("Search task is not running")

            if results.search_id != search_id:
                raise ValueError("Search ID mismatch")

            saved = results.model_copy(deep=True)
            saved.status = TaskStatus.COMPLETED.value

            self._results[search_id] = saved

            task.status = TaskStatus.COMPLETED
            task.error = None
            task.updated_at = datetime.now(timezone.utc)

            return task.model_copy(deep=True)

    def get_results(
        self,
        search_id: str,
    ) -> JobSearchResultsResponse | None:
        with self._lock:
            task = self._tasks.get(search_id)

            if task is None:
                return None

            stored = self._results.get(search_id)

            if stored is None:
                return JobSearchResultsResponse(
                    search_id=search_id,
                    status=task.status.value,
                )

            result = stored.model_copy(deep=True)
            result.status = task.status.value

            return result



task_manager = SearchTaskManager()
