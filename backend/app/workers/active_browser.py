"""Unrestricted discovery only with explicit platform authorization. No evasion."""
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from scrapling.parser import Selector

from backend.app.config import settings
from backend.app.schemas.job import JobSource
from backend.app.services.job_deduplication import job_identity
from backend.app.services.job_pipeline import JobExtractionPipeline, PipelineResult
from backend.app.services.active_job_details import enrich_active_details, matches_active_posting_window
from backend.app.workers.active_jobs import SourceUnavailable


def discovery_url(source):
    if source == JobSource.LINKEDIN:
        return "https://www.linkedin.com/jobs/search/?sortBy=DD&f_TPR=r86400"
    if source == JobSource.WELLFOUND:
        # No documented universal newest-first parameter. Never invent one or
        # use the old fixed role/location mappings. Validate dates on details.
        return "https://wellfound.com/jobs"
    raise ValueError("Unsupported Active Jobs source")


def collect_active_source(collector, source, search, progress):
    url = discovery_url(source)
    collector.check_cancelled()
    if not settings.ACTIVE_JOBS_AUTHORIZATIONS.get(source.value, "").strip():
        collector.browser_opener(url)
        progress("browser_action", {"action": "manual_required"})
        raise SourceUnavailable("authorization_required")

    result = PipelineResult(source=source)
    pipeline = JobExtractionPipeline()
    errors = []
    delay = round(search.watch_delay_seconds * 1000) if search.watch_mode else 1500
    allowed_hosts = {f"{source.value}.com", f"www.{source.value}.com"}

    def setup(page):
        def route_guard(route):
            request = route.request
            if request.is_navigation_request() and request.frame == page.main_frame:
                target = urlsplit(request.url)
                if (target.scheme != "https" or target.hostname not in allowed_hosts
                        or target.username or target.password or target.port not in (None, 443)
                        or not target.path.startswith("/jobs")):
                    errors.append(SourceUnavailable("access_blocked"))
                    route.abort()
                    return
            route.fallback()
        page.route("**/*", route_guard)
        def check_response(response):
            if response.request.is_navigation_request() and response.request.frame == page.main_frame and response.status >= 400:
                errors.append(SourceUnavailable("access_blocked" if response.status in (401, 403, 429) else "failed"))
        page.on("response", check_response)

    def action(page):
        try:
            page.set_default_timeout(collector.timeout_ms)
            def guard():
                collector.check_cancelled()
                if errors:
                    raise errors[0]
                if urlsplit(page.url).hostname not in allowed_hosts:
                    raise SourceUnavailable("access_blocked")
                if (page.locator('input[type="password"]:visible, iframe[src*="captcha"]:visible, #challenge-form:visible, form[action*="checkpoint"]:visible').count()
                    or re.search(r'access denied|just a moment|security verification|sign in|log in', page.title(), re.I)):
                    raise SourceUnavailable("access_blocked")
            def done(name):
                guard()
                progress("browser_action", {"action": name})
                page.wait_for_timeout(delay)
                guard()
            guard()
            done("opened_source")
            # Use an actual exposed sort control when present; no fabricated URL
            # parameters or assumptions about Wellfound's default ordering.
            if source == JobSource.WELLFOUND:
                for select in page.locator("select").all():
                    options = select.locator("option").all()
                    newest = next((o for o in options if re.fullmatch(r'newest(?: first)?|most recent', o.inner_text().strip(), re.I)), None)
                    if newest is not None:
                        select.select_option(label=newest.inner_text().strip())
                        done("submitted_search")
                        break
            listing_url = page.url
            seen = set()
            # Bounded scrolling, including newly loaded cards. Every new URL is
            # inspected before further scrolling, so saves begin immediately.
            for page_number in range(1, 11):
                guard()
                page.wait_for_load_state("domcontentloaded")
                urls = pipeline.discover_urls(source, search, page.content())
                fresh = [u for u in urls if job_identity(source, u) not in seen]
                if not fresh:
                    if page_number == 1 and not page.locator('.jobs-search-no-results-banner, [data-testid="no-results"]').count():
                        raise SourceUnavailable("failed")
                    break
                seen.update(job_identity(source, u) for u in fresh)
                result.discovered_urls.extend(fresh)
                progress("page_discovered", {"page_number": page_number,
                    "new_jobs_discovered": len(fresh), "total_discovered": len(seen)})
                done("inspected_results")
                for job_url in fresh:
                    guard()
                    page.goto(job_url, wait_until="domcontentloaded")
                    done("opened_listing")
                    page.locator("h1").first.wait_for(state="visible")
                    more = page.get_by_role("button", name=re.compile(r"^show more(?: description)?$", re.I))
                    if more.count() and more.first.is_visible():
                        more.first.click()
                    page.mouse.wheel(0, 500)
                    done("inspected_description")
                    html = Selector(content=page.content())
                    adapter = pipeline.adapters[source]
                    try:
                        job = adapter.extract_job_details(html, job_url)
                        structured = (adapter._get_structured_job(html) if source == JobSource.LINKEDIN
                                      else adapter._structured_job(html))
                        now = datetime.now(timezone.utc)
                        enrich_active_details(job, html, structured, now)
                    except Exception:
                        # Parser errors affect one listing. Access gates were
                        # checked above and always stop the source.
                        progress("job_failed", {"job_url": job_url,
                            "error": "Job detail fetching or extraction failed", "total_failed": 1})
                        continue
                    if matches_active_posting_window(job, now):
                        result.jobs.append(job)
                        progress("job_collected", {"job": job})
                    else:
                        done("filtered_job")
                    if len(result.jobs) >= search.max_results:
                        return
                page.goto(listing_url, wait_until="domcontentloaded")
                done("returned_results")
                # Scroll progressively after returning from details. Stop as soon
                # as the source exposes no new links; do not brute-force endpoints.
                for _ in range(page_number):
                    page.mouse.wheel(0, 1200)
                    done("scrolled_listing")
        except Exception as exc:
            errors.append(exc)

    # Active Jobs always uses visible Chrome; Watch controls action pacing.
    with collector.session_factory(headless=False, real_chrome=True, network_idle=False, retries=1) as session:
        response = session.fetch(url, google_search=False, timeout=collector.timeout_ms,
                                 page_setup=setup, page_action=action)
        if errors:
            raise errors[0]
        if response.status >= 300:
            raise SourceUnavailable("access_blocked" if response.status in (401, 403, 429) else "failed")
    return result
