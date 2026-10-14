"""Small, allow-listed public payloads; never serialize browser objects/errors."""

from collections.abc import Callable
from typing import Literal
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

ProgressCallback = Callable[[str, dict], None]
TERMINAL_EVENTS = frozenset({"search_completed", "search_failed"})
JOB_FAILURE_MESSAGE = "Job detail fetching or extraction failed"
SEARCH_FAILURE_MESSAGE = "Search execution failed"


class EventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SearchQueued(EventPayload):
    search_id: str
    status: Literal["pending"]
    source: str


class SearchStarted(EventPayload):
    search_id: str
    status: Literal["running"]
    source: str


class PageDiscovered(EventPayload):
    page_number: int = Field(ge=1)
    new_jobs_discovered: int = Field(ge=0)
    total_discovered: int = Field(ge=0)


class JobPayload(EventPayload):
    job_url: str

    @field_validator("job_url")
    @classmethod
    def public_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Expected a public job URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("Credentials are forbidden in event URLs")
        # Tracking parameters and fragments can contain session tokens.
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


class JobExtracted(JobPayload):
    title: str = Field(max_length=500)
    company: str = Field(max_length=500)
    total_extracted: int = Field(ge=1)

    @field_validator("title", "company")
    @classmethod
    def plain_text(cls, value: str) -> str:
        if "<" in value or ">" in value:
            raise ValueError("Event text must not contain HTML")
        return value


class JobFailed(JobPayload):
    # Only public summaries: arbitrary exception text may contain HTML/secrets.
    error: Literal["Job detail fetching or extraction failed", "Job description unavailable"]
    total_failed: int = Field(ge=1)


class SearchCompleted(EventPayload):
    search_id: str
    status: Literal["completed"]
    total_discovered: int = Field(ge=0)
    total_extracted: int = Field(ge=0)
    total_failed: int = Field(ge=0)


class SearchFailed(EventPayload):
    search_id: str
    status: Literal["failed"]
    error: Literal["Search execution failed", "Browser execution failed"]


class JobSaved(EventPayload):
    job_id: str
    source: Literal["linkedin", "wellfound", "careerhub", "greenhouse", "ashby", "lever", "remotive", "usajobs"]
    total_extracted: int = Field(ge=1)

    @field_validator("job_id")
    @classmethod
    def uuid_id(cls, value):
        return str(UUID(value))


class SourceStatus(EventPayload):
    source: Literal["linkedin", "wellfound", "careerhub", "greenhouse", "ashby", "lever", "remotive", "usajobs"]
    status: Literal["collecting", "completed", "authorization_required", "access_blocked", "failed", "limit_reached", "disabled"]
    scanned: int = Field(default=0, ge=0)
    saved: int = Field(default=0, ge=0)
    undated: int = Field(default=0, ge=0)
    error: str | None = None


EVENT_PAYLOADS: dict[str, type[EventPayload]] = {
    "source_status": SourceStatus,
    "job_saved": JobSaved,
    "search_queued": SearchQueued,
    "search_started": SearchStarted,
    "page_discovered": PageDiscovered,
    "job_extracted": JobExtracted,
    "job_failed": JobFailed,
    "search_completed": SearchCompleted,
    "search_failed": SearchFailed,
}


def validate_payload(search_id: UUID, event_type: str, payload: dict) -> dict:
    model = EVENT_PAYLOADS.get(event_type)
    if model is None:
        raise ValueError(f"Unknown search event type: {event_type}")
    data = model.model_validate(payload).model_dump(mode="json")
    if "search_id" in data and data["search_id"] != str(search_id):
        raise ValueError("Event search_id must match its parent search")
    return data
