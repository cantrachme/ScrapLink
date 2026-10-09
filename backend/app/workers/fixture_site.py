"""Explicit development fixture transport; production source URLs stay canonical."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

from scrapling.fetchers import DynamicSession

from backend.app.schemas.job import JobSource
from backend.app.services.job_deduplication import extract_job_id
from backend.app.workers.browser_collector import BrowserCollector

FIXTURE_ROOT = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "e2e"
DEMO_IDS = ("990000000000000000000000000000000001", "990000000000000000000000000000000002",
            "990000000000000000000000000000000003", "990000000000000000000000000000000004")


class FixtureSite:
    def __init__(self, origin: str, job_ids: tuple[str, ...] = DEMO_IDS):
        parsed = urlsplit(origin)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port or parsed.path:
            raise ValueError("Fixture origin must be http://127.0.0.1:PORT")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Invalid fixture origin")
        self.origin = origin
        self.job_ids = job_ids

    def resolve(self, url: str) -> str:
        parsed = urlsplit(url)
        for source in (JobSource.LINKEDIN, JobSource.WELLFOUND):
            if not BrowserCollector._is_allowed_job_url(source, url):
                continue
            if source == JobSource.LINKEDIN and parsed.path.rstrip("/") == "/jobs/search":
                query = parse_qs(parsed.query)
                if (query.get("keywords", [""])[0].casefold() != "python developer"
                        or query.get("location", [""])[0].casefold() not in {"", "united states", "new york"}):
                    raise ValueError("Fixture searches support Python Developer in United States or New York only")
                page = int(query.get("start", ["0"])[0]) // 25 + 1
                return f"{self.origin}/{source.value}/listing-{min(page, 3)}.html"
            if source == JobSource.WELLFOUND and parsed.path.startswith("/role/"):
                if parsed.path not in {"/role/python-developer", "/role/l/python-developer/united-states",
                                       "/role/l/python-developer/new-york"}:
                    raise ValueError("Fixture searches support Python Developer in United States or New York only")
                page = int(parse_qs(parsed.query).get("page", ["1"])[0])
                return f"{self.origin}/{source.value}/listing-{min(page, 3)}.html"
            job_id = extract_job_id(source, url)
            if job_id in self.job_ids:
                index = self.job_ids.index(job_id) + 1
                return f"{self.origin}/{source.value}/detail-{index}.html"
        raise ValueError("URL is outside the explicit fixture catalog")

    def response(self, path: str) -> tuple[int, bytes]:
        # A fixed catalog avoids directory traversal and arbitrary file serving.
        allowed = {f"/{source}/{kind}-{number}.html"
                   for source in ("linkedin", "wellfound")
                   for kind in ("listing", "detail") for number in (1, 2, 3)}
        if path not in allowed:
            return 403, b"Demonstration: intentionally inaccessible detail"
        html = (FIXTURE_ROOT / path.lstrip("/")).read_text()
        for number, job_id in enumerate(self.job_ids, 1):
            html = html.replace(f"__JOB_{number}__", job_id)
        return 200, html.encode()

    @contextmanager
    def browser_session(self, **options):
        # Install context-wide routes before the first navigation. Unlike
        # Scrapling page_setup, setup errors here cannot be swallowed.
        with DynamicSession(
            **options, retries=1,
            additional_args={"service_workers": "block", "java_script_enabled": False},
            extra_flags=["--disable-background-networking", "--disable-component-update",
                         "--disable-sync", "--no-first-run",
                         "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1"],
        ) as session:
            session.context.route("**/*", self.route_request)
            session.context.route_web_socket("**/*", lambda socket: socket.close())
            yield session

    def route_request(self, route):
        parsed = urlsplit(route.request.url)
        if (parsed.scheme == "http" and parsed.netloc == urlsplit(self.origin).netloc
                and not parsed.username and not parsed.password):
            route.continue_()
        else:
            route.abort("blockedbyclient")


@contextmanager
def fixture_server(port: int = 8765, *, job_ids: tuple[str, ...] = DEMO_IDS):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            status, body = site.response(urlsplit(self.path).path)
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'none'; connect-src 'none'")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    site = FixtureSite(f"http://127.0.0.1:{server.server_port}", job_ids)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield site
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
