import logging
import math
from contextlib import ExitStack
from datetime import timedelta
from threading import Event
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from backend.app.database import SessionLocal
from backend.app.models.search import SearchTaskRecord
from backend.app.repositories.search_event_repository import SearchEventRepository
from backend.app.repositories.search_repository import SearchRepository, utc_now
from backend.app.schemas.search_event import SEARCH_FAILURE_MESSAGE
from backend.app.workers.execution_lock import execution_lock, lock_key

logger = logging.getLogger(__name__)
STALE_TIMEOUT_SECONDS = 300.0


class WorkerShutdown(Exception):
    """Cooperative cancellation, distinct from a process crash."""


class JobQueueWorker:
    """PostgreSQL queue; injected collectors keep tests browser-independent."""

    def __init__(self, collector, *, stop_event: Event | None = None):
        self.collector = collector
        self.repository = SearchRepository()
        self.events = SearchEventRepository()
        self.stop_event = stop_event if stop_event is not None else Event()

    def check_shutdown(self) -> None:
        if self.stop_event.is_set():
            raise WorkerShutdown("Worker stopped by operator; search was not retried")

    def _fail(self, db, search_id: UUID, error: str) -> bool:
        task = self.repository._get_locked(db, search_id)
        if task.status != "running":
            return False  # Fences a late collector after recovery; no second terminal event.
        self.repository.fail(db, search_id, error)
        self.events.publish(db, search_id, "search_failed", {
            "search_id": str(search_id), "status": "failed", "error": SEARCH_FAILURE_MESSAGE,
        })
        return True

    def recover_stale(
        self, stale_timeout_seconds: float = STALE_TIMEOUT_SECONDS,
        *, search_id: UUID | None = None,
    ) -> int:
        """Fail abandoned searches once, retaining their durable progress log.

        The row lock serializes terminal writes. The transaction advisory lock
        proves no worker holds execution ownership, even if progress is slow.
        This never resets a task to pending or automatically repeats collection.
        """
        if not math.isfinite(stale_timeout_seconds) or stale_timeout_seconds <= 0:
            raise ValueError("Stale timeout must be positive and finite")
        cutoff = utc_now() - timedelta(seconds=stale_timeout_seconds)
        recovered = 0
        with SessionLocal.begin() as db:
            statement = select(SearchTaskRecord).where(
                SearchTaskRecord.status == "running", SearchTaskRecord.updated_at < cutoff,
                SearchTaskRecord.request_payload["mode"].as_string() == "discovery",
            ).order_by(SearchTaskRecord.updated_at).with_for_update(skip_locked=True).limit(100)
            if search_id is not None:
                statement = statement.where(SearchTaskRecord.search_id == search_id)
            for task in db.scalars(statement):
                if db.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {
                    "key": lock_key(task.search_id),
                }):
                    recovered += self._fail(db, task.search_id,
                        "Worker execution was abandoned (ownership lock lost and stale timeout exceeded); "
                        "progress retained, search not retried")
        if recovered:
            logger.warning("Recovered %s abandoned searches as failed", recovered)
        return recovered

    def run_once(self, search_id: UUID | None = None) -> bool:
        """Claim and process one pending task; False means no eligible work."""
        if self.stop_event.is_set():
            return False
        with ExitStack() as ownership:
            with SessionLocal.begin() as db:
                task = self.repository.claim_next_pending(db, search_id=search_id, mode="discovery")
                if task is None:
                    return False
                claimed_id = task.search_id
                # Acquire ownership before the running status becomes visible.
                ownership.enter_context(execution_lock(claimed_id))
                request_payload = dict(task.request_payload)
                self.events.publish(db, claimed_id, "search_started", {
                    "search_id": str(claimed_id), "status": "running", "source": "multi",
                })
            try:
                self.check_shutdown()
                from backend.app.workers.discovery import run_discovery
                run_discovery(self, claimed_id, request_payload)
                logger.info("Finished search %s (%s)", claimed_id, task.status)
            except (Exception, KeyboardInterrupt) as exc:
                if isinstance(exc, (WorkerShutdown, KeyboardInterrupt)):
                    self.stop_event.set()
                    error = "Worker stopped by operator; progress retained, search not retried"
                    logger.info("Interrupted search %s", claimed_id)
                else:
                    error = f"{type(exc).__name__}: {exc}"
                    logger.exception("Search %s failed", claimed_id)
                with SessionLocal.begin() as db:
                    self._fail(db, claimed_id, error)
        return True

    def run_forever(
        self, poll_interval_seconds: float = 2.0,
        stale_timeout_seconds: float = STALE_TIMEOUT_SECONDS,
    ) -> None:
        if not math.isfinite(poll_interval_seconds) or poll_interval_seconds <= 0:
            raise ValueError("Polling interval must be positive and finite")
        logger.info("ScrapLink queue worker started")
        try:
            while not self.stop_event.is_set():
                try:
                    self.recover_stale(stale_timeout_seconds)
                    processed = self.run_once()
                except SQLAlchemyError:
                    # Do not retry the claimed search. Recovery will audit any
                    # abandoned running task after DB connectivity returns.
                    logger.exception("Database unavailable; queue polling will resume")
                    processed = False
                if not processed:
                    self.stop_event.wait(poll_interval_seconds)
        except KeyboardInterrupt:
            self.stop_event.set()
        finally:
            logger.info("ScrapLink queue worker stopped")
