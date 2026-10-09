"""Visible UI collection. No fixture resolver or off-site job navigation."""
import re
import subprocess
import sys
import webbrowser
from urllib.parse import urljoin, urlsplit

from scrapling.fetchers import DynamicSession
from scrapling.parser import Selector

from backend.app.schemas.job import JobListing, JobSource
from backend.app.services.job_filters import matches_posting_window
from backend.app.services.job_pipeline import PipelineResult

CAREERHUB = "https://careerhub.za-worknow.com"
ASSISTED_SITES = {
    JobSource.LINKEDIN: "https://www.linkedin.com/jobs/",
    JobSource.WELLFOUND: "https://wellfound.com/jobs",
}


def open_chrome(url):
    # Ordinary browser navigation only; users operate restricted sites themselves.
    if sys.platform == "darwin":
        subprocess.run(["open", "-a", "Google Chrome", url], check=True)
    elif not webbrowser.get("google-chrome").open(url):
        raise RuntimeError("Could not open Google Chrome")


def careerhub_job(html, url):
    page = Selector(content=html)
    def text(selector):
        nodes = page.css(selector)
        return str(nodes[0].get_all_text(separator="\n", strip=True)).strip() if nodes else None
    return JobListing(
        source=JobSource.CAREERHUB, job_url=url, title=text("h1") or "",
        company=text(".job-row__company") or "", location=text("dl .job-row__location"),
        workplace_type={"Remote": "remote", "Hybrid": "hybrid", "On-site": "onsite"}.get(text(".type-badge--workplace")),
        description=text(".detail-copy"),
    )


class LiveBrowserCollector:
    """CareerHub permits non-disruptive public crawling; other sources are manual.

    Keep all navigation inside one Scrapling page_action, using its Playwright
    page. Scrapling catches callback exceptions, so explicitly propagate them.
    """
    def __init__(self, *, headless=False, timeout_ms=30000, check_cancelled=lambda: None,
                 session_factory=DynamicSession, browser_opener=open_chrome):
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.check_cancelled = check_cancelled
        self.session_factory = session_factory
        self.browser_opener = browser_opener

    def collect_with_progress(self, source, search, progress=None):
        if source.value != search.source:
            raise ValueError("Search request source must match collector source")
        result = PipelineResult(source=source)
        def emit(action):
            if progress:
                progress("browser_action", {"action": action})
        self.check_cancelled()
        if source in ASSISTED_SITES:
            self.browser_opener(ASSISTED_SITES[source])
            emit("manual_required")
            return result
        if source != JobSource.CAREERHUB:
            raise ValueError("Unsupported live source; use an assisted source")
        # Respect the source's non-disruptive access policy even with Watch off.
        delay = int(search.watch_delay_seconds * 1000) if search.watch_mode else 1500
        errors = []
        def setup(page):
            def guard(route):
                request = route.request
                if request.is_navigation_request() and request.frame == page.main_frame:
                    url = urlsplit(request.url)
                    if url.scheme != "https" or url.netloc != urlsplit(CAREERHUB).netloc or not url.path.startswith("/jobs"):
                        errors.append(RuntimeError("Off-source navigation blocked; no external listing was fetched"))
                        route.abort()
                        return
                route.fallback()
            page.route("**/*", guard)
            def response_check(response):
                if response.request.is_navigation_request() and response.request.frame == page.main_frame and response.status >= 400:
                    errors.append(RuntimeError(f"Source unavailable (HTTP {response.status}); collection stopped"))
            page.on("response", response_check)
        def action(page):
            try:
                if errors:
                    raise errors[0]
                self._collect(page, search, result, emit, progress, delay, errors)
            except Exception as exc:
                errors.append(exc)
        with self.session_factory(headless=False if search.watch_mode else self.headless,
                                  real_chrome=True, network_idle=False, retries=1) as session:
            response = session.fetch(f"{CAREERHUB}/jobs", google_search=False,
                                     timeout=self.timeout_ms, page_setup=setup, page_action=action)
            if errors:
                raise errors[0]
            if response.status >= 300:
                raise RuntimeError(f"Source unavailable (HTTP {response.status}); no jobs saved")
        return result

    def __call__(self, source, search):
        return self.collect_with_progress(source, search)

    def _collect(self, page, search, result, emit, progress, delay, errors):
        page.set_default_timeout(self.timeout_ms)
        def gate():
            self.check_cancelled()
            if errors:
                raise errors[0]
            if urlsplit(page.url).hostname != urlsplit(CAREERHUB).hostname:
                raise RuntimeError("Off-source navigation stopped; use the assisted workflow")
            if (page.locator('input[type="password"]:visible, iframe[src*="captcha"]:visible, #challenge-form:visible').count()
                or re.search(r'access denied|just a moment|security verification|cloudflare.*error', page.title(), re.I)):
                raise RuntimeError("Login or access challenge; stopped without bypassing restrictions")
        def done(event):
            gate()
            emit(event)  # Only after the browser action actually succeeds.
            page.wait_for_timeout(delay)
            self.check_cancelled()
        gate()
        field = page.get_by_role("searchbox", name="Search", exact=True)
        field.wait_for(state="visible")
        done("opened_source")
        field.click()
        done("focused_keyword")
        field.fill("")
        field.press_sequentially(search.keyword, delay=80 if search.watch_mode else 0)
        done("typed_keyword")
        # This source has no separate location input. Never invent a control or
        # silently alter the keyword; announce and apply location to parsed jobs.
        if search.location:
            emit("location_filter_local")
        with page.expect_navigation(wait_until="domcontentloaded"):
            page.get_by_role("button", name="Apply filters", exact=True).click()
        done("submitted_search")
        page.locator(".filter-bar").wait_for(state="visible")
        # Loaded result heading and empty state are source-specific evidence.
        page.locator(".job-list, .empty-state").first.wait_for(state="visible")
        gate()
        links = page.locator(".job-row__title a")
        urls = []
        for href in links.evaluate_all("nodes => nodes.map(n => n.getAttribute('href'))"):
            url = urljoin(CAREERHUB, href or "")
            parsed = urlsplit(url)
            if (parsed.scheme == "https" and parsed.netloc == urlsplit(CAREERHUB).netloc
                and re.fullmatch(r"/jobs/[^/]+", parsed.path) and url not in urls):
                urls.append(url)
        if not urls and not page.locator(".empty-state").count():
            raise RuntimeError("Unrecognized source results; no jobs saved")
        result.discovered_urls.extend(urls)
        if progress:
            progress("page_discovered", {"page_number": 1, "new_jobs_discovered": len(urls), "total_discovered": len(urls)})
        done("inspected_results")
        # A single search page, at most 20 detail visits. No bulk crawling.
        for url in urls[:20]:
            gate()
            link = page.locator(f'.job-row__title a[href="{urlsplit(url).path}"]')
            link.scroll_into_view_if_needed()
            done("scrolled_listing")
            with page.expect_navigation(wait_until="domcontentloaded"):
                link.click()
            page.locator("h1").wait_for(state="visible")
            done("opened_listing")
            description = page.locator(".detail-copy")
            if description.count():
                description.scroll_into_view_if_needed()
                page.mouse.wheel(0, 450)
            done("inspected_description")
            job = careerhub_job(page.content(), url)
            location_match = not search.location or search.location.casefold() in (job.location or "").casefold()
            if location_match and matches_posting_window(job, search.date_posted):
                result.jobs.append(job)
                if progress:
                    progress("job_extracted", {"job_url": job.job_url, "title": job.title, "company": job.company,
                                               "total_extracted": result.total_extracted})
            else:
                emit("filtered_job")
            if result.total_extracted >= search.max_results:
                break
            page.go_back(wait_until="domcontentloaded")
            page.locator(".filter-bar").wait_for(state="visible")
            done("returned_results")
