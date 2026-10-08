
from datetime import datetime, timezone
from enum import Enum
from threading import Lock
from uuid import uuid4

from pydantic import BaseModel, Field

from backend.app.schemas.job import JobSearchRequest


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


task_manager = SearchTaskManager()
