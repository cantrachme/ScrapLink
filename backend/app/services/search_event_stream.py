"""PostgreSQL polling with short, off-event-loop reads and session-free waits."""

import asyncio
import json
from collections.abc import AsyncIterator
from time import monotonic
from uuid import UUID

from fastapi import Request
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from backend.app.database import SessionLocal
from backend.app.models.search import SearchTaskRecord
from backend.app.repositories.search_event_repository import (
    SearchEventData,
    SearchEventRepository,
)
from backend.app.schemas.search_event import TERMINAL_EVENTS

POLL_INTERVAL_SECONDS = 1.0
HEARTBEAT_INTERVAL_SECONDS = 15.0
BATCH_SIZE = 100


def read_event_batch(search_id: UUID, after: int) -> tuple[list[SearchEventData], bool]:
    # Both the thread pool and the shared SQLAlchemy pool have bounded capacity.
    # The session is closed before returning DTOs to the streaming coroutine.
    with SessionLocal() as db:
        status = db.scalar(select(SearchTaskRecord.status).where(
            SearchTaskRecord.search_id == search_id,
        ))
        if status is None:
            raise KeyError("Search task not found")
        events = SearchEventRepository.get_after(db, search_id, after, limit=BATCH_SIZE)
        return events, status in {"completed", "failed"}


def format_event(event: SearchEventData) -> str:
    data = json.dumps(event.payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return f"id: {event.sequence}\nevent: {event.event_type}\ndata: {data}\n\n"


async def stream_search_events(
    request: Request, search_id: UUID, after: int,
) -> AsyncIterator[str]:
    last_sent = monotonic()
    while not await request.is_disconnected():
        try:
            events, terminal = await run_in_threadpool(read_event_batch, search_id, after)
        except KeyError:
            # Parent was removed after the route's preflight existence check.
            return
        for event in events:
            if await request.is_disconnected():
                return
            yield format_event(event)
            after = event.sequence
            terminal = terminal or event.event_type in TERMINAL_EVENTS
            last_sent = monotonic()
        if terminal and len(events) < BATCH_SIZE:
            return
        if len(events) == BATCH_SIZE:
            continue  # Drain replay without imposing a delay per batch.
        if not events and monotonic() - last_sent >= HEARTBEAT_INTERVAL_SECONDS:
            yield ": heartbeat\n\n"
            last_sent = monotonic()
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
