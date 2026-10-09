"""Process ownership without a database transaction spanning browser work."""

from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import text

from backend.app.database import engine


def lock_key(search_id: UUID) -> int:
    # Advisory locks take a signed bigint. A collision only delays recovery;
    # it cannot permit two owners. Reserve a stable key across worker restarts.
    return int.from_bytes(search_id.bytes[:8], byteorder="big", signed=True)


@contextmanager
def execution_lock(search_id: UUID):
    # AUTOCOMMIT is essential: this connection is idle, never idle-in-transaction.
    # Physically close it on exit so session locks cannot leak into the pool,
    # including when a connection error makes explicit unlock unreliable.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        try:
            acquired = connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {
                "key": lock_key(search_id),
            })
            if not acquired:
                raise RuntimeError("Search execution is already owned by another worker")
            yield
        finally:
            connection.invalidate()
