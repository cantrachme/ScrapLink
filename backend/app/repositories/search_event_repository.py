import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models.search import SearchTaskRecord
from backend.app.models.search_event import SearchEvent
from backend.app.schemas.search_event import validate_payload


@dataclass(frozen=True)
class SearchEventData:
    """Independent of the session; safe to pass into an async stream."""

    search_id: UUID
    sequence: int
    event_type: str
    payload: dict
    created_at: datetime


def serialize(event: SearchEvent) -> SearchEventData:
    return SearchEventData(
        event.search_id, event.sequence, event.event_type,
        json.loads(json.dumps(event.payload, allow_nan=False)), event.created_at,
    )


class SearchEventRepository:
    @staticmethod
    def publish(
        db: Session, search_id: UUID, event_type: str, payload: dict,
    ) -> SearchEventData:
        search_id = UUID(str(search_id))
        data = validate_payload(search_id, event_type, payload)
        # Validate JSON before touching the transaction (NaN is not valid JSON).
        data = json.loads(json.dumps(data, allow_nan=False))
        parent = db.scalar(
            select(SearchTaskRecord.search_id)
            .where(SearchTaskRecord.search_id == search_id)
            .with_for_update()
        )
        if parent is None:
            raise KeyError("Search task not found")
        # Separate statement after the lock: READ COMMITTED sees the previous
        # publisher's commit. Flush below also handles repeated publishes in
        # one transaction despite SessionLocal's autoflush=False.
        last_sequence = db.scalar(
            select(func.max(SearchEvent.sequence))
            .where(SearchEvent.search_id == search_id)
        ) or 0
        event = SearchEvent(
            search_id=search_id, sequence=last_sequence + 1,
            event_type=event_type, payload=data,
        )
        db.add(event)
        db.flush()
        return serialize(event)

    @staticmethod
    def get_after(
        db: Session, search_id: UUID, after_sequence: int, limit: int = 100,
    ) -> list[SearchEventData]:
        if type(after_sequence) is not int or after_sequence < 0:
            raise ValueError("after_sequence must be a nonnegative integer")
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        search_id = UUID(str(search_id))
        if db.scalar(select(SearchTaskRecord.search_id).where(
            SearchTaskRecord.search_id == search_id,
        )) is None:
            raise KeyError("Search task not found")
        events = db.scalars(
            select(SearchEvent)
            .where(SearchEvent.search_id == search_id, SearchEvent.sequence > after_sequence)
            .order_by(SearchEvent.sequence)
            .limit(limit)
        ).all()
        return [serialize(event) for event in events]
