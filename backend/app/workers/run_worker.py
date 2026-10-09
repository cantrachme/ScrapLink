"""Run with python -m backend.app.workers.run_worker --help."""

import argparse
import logging
import math
import signal
from contextlib import ExitStack
from threading import Event

from backend.app.config import settings
from backend.app.sources.search_router import build_source_search_url
from backend.app.workers.browser_collector import BrowserCollector
from backend.app.workers.live_browser import LiveBrowserCollector
from backend.app.workers.fixture_site import fixture_server
from backend.app.workers.queue_worker import JobQueueWorker, WorkerShutdown

logger = logging.getLogger(__name__)


def positive(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be positive and finite")
    return number


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description="ScrapLink independent PostgreSQL queue worker")
    cli.add_argument("--mode", choices=("fixture", "live"), required=True,
                     help="fixture: isolated tests only; live: visible browser and assisted sources")
    cli.add_argument("--once", action="store_true", help="recover stale tasks, process at most one pending task, exit")
    cli.add_argument("--poll-interval", type=positive, default=2.0, metavar="SECONDS")
    cli.add_argument("--stale-timeout", type=positive, default=300.0, metavar="SECONDS")
    cli.add_argument("--headless", action=argparse.BooleanOptionalAction, default=settings.BROWSER_HEADLESS,
                     help="hide Chrome (visible by default)")
    cli.add_argument("--max-pages", type=int, default=10, help="fixture pagination limit; live CareerHub uses one results page")
    cli.add_argument("--fixture-port", type=int, default=8765, help="loopback fixture server port (0 chooses a free port)")
    cli.add_argument("--recover-only", action="store_true", help="recover abandoned searches without opening Chrome")
    return cli


def main(argv: list[str] | None = None) -> int:
    cli = parser()
    args = cli.parse_args(argv)
    if args.max_pages < 1:
        cli.error("--max-pages must be positive")
    if not 0 <= args.fixture_port <= 65535:
        cli.error("--fixture-port must be between 0 and 65535")
    if args.mode == "fixture" and settings.APP_ENV != "test":
        cli.error("fixture mode requires APP_ENV=test")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    stop = Event()

    def shutdown(signum, frame):
        logger.info("Shutdown requested; stopping at the next browser boundary")
        stop.set()

    previous = {sig: signal.signal(sig, shutdown) for sig in (signal.SIGINT, signal.SIGTERM)}
    logger.info("Starting worker mode=%s browser=%s", args.mode, "hidden" if args.headless else "visible")
    try:
        with ExitStack() as stack:
            def check_cancelled():
                if stop.is_set():
                    raise WorkerShutdown()

            collector = LiveBrowserCollector(headless=args.headless,
                check_cancelled=check_cancelled, timeout_ms=settings.BROWSER_TIMEOUT_MS)
            if args.mode == "fixture" and not args.recover_only:
                site = stack.enter_context(fixture_server(args.fixture_port))
                logger.warning("ISOLATED TEST FIXTURES ONLY: %s", site.origin)
                collector = BrowserCollector(build_source_search_url,
                    session_factory=site.browser_session, navigation_url_resolver=site.resolve,
                    headless=args.headless, max_pages=args.max_pages,
                    check_cancelled=check_cancelled, timeout_ms=settings.BROWSER_TIMEOUT_MS)
            worker = JobQueueWorker(collector, stop_event=stop)
            if args.once or args.recover_only:
                worker.recover_stale(args.stale_timeout)
                if not args.recover_only and not worker.run_once():
                    logger.info("No pending searches")
            else:
                worker.run_forever(args.poll_interval, args.stale_timeout)
        return 0
    except Exception:
        logger.exception("Worker stopped due to an error")
        return 1
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        logger.info("Worker shutdown complete")


if __name__ == "__main__":
    raise SystemExit(main())
