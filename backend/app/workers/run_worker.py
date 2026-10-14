"""Headless public discovery worker; no browser or fixture execution modes."""
import logging
import signal
from threading import Event

from backend.app.sources.discovery import PublicCollector
from backend.app.workers.execution_lock import execution_lock
from backend.app.workers.queue_worker import JobQueueWorker
from uuid import UUID

# Shared with the API's liveness probe; session ownership ends on process death.
WORKER_ID = UUID('53435241-504c-494e-8000-000000000001')


def main():
    logging.basicConfig(level=logging.INFO)
    stop = Event()
    worker = JobQueueWorker(PublicCollector(), stop_event=stop)
    worker.collector.check_cancelled = worker.check_shutdown
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    with execution_lock(WORKER_ID):
        # With exclusive worker ownership, any previously running task is abandoned.
        worker.recover_stale(0.001)
        worker.run_forever(poll_interval_seconds=1)


if __name__ == '__main__':
    main()
