"""Additional published evidence for Active Jobs; never infer missing fields."""
import re
from datetime import datetime, timedelta, timezone

from scrapling.parser import Selector

from backend.app.schemas.job import Compensation, JobStatus, WorkplaceType
from backend.app.services.job_filters import matches_posting_window, parse_posting_date
from backend.app.sources.structured_job import workplace_type


def enrich_active_details(job, page: Selector, structured: dict, now):
    def first(selectors):
        for selector in selectors:
            nodes = page.css(selector)
            if nodes:
                value = str(nodes[0].get_all_text(separator="\n", strip=True)).strip()
                if value:
                    return value
        return None
    job.posted_text = first(['.posted-time-ago__text', '[data-testid="job-posted-date"]', 'time'])
    if job.posted_at is None and job.posted_date is None:
        value = page.css('time[datetime]::attr(datetime)').get()
        job.posted_date, job.posted_at = parse_posting_date(value)
    salary = first(['.compensation__salary', '[data-testid="job-salary"]', '[itemprop="baseSalary"]'])
    if salary:
        job.compensation = job.compensation or Compensation()
        job.compensation.raw_text = salary
    if job.workplace_type is None:
        published = first(['[data-testid="remote-work-policy"]', '[data-testid="workplace-type"]'])
        job.workplace_type = workplace_type(published) or {"on-site": WorkplaceType.ONSITE, "on site": WorkplaceType.ONSITE}.get((published or '').casefold())
    expiry_date, expiry_at = parse_posting_date(structured.get('validThrough'))
    if (expiry_at is not None and expiry_at < now) or (expiry_date is not None and expiry_date < now.date()) or page.css('.closed-job__flavor, [data-testid="job-closed"]'):
        job.status = JobStatus.CLOSED
    job.last_verified_at = now
    return job


def matches_active_posting_window(job, now=None):
    reference = now or datetime.now(timezone.utc)
    if job.status == JobStatus.CLOSED:
        return False
    if job.posted_at is not None or job.posted_date is not None:
        return matches_posting_window(job, '24h', reference)
    # Preserve relative source text, with no invented timestamp. Use an upper
    # age bound so rounded '24 hours ago' cannot be called within 24 hours.
    match = re.fullmatch(r'(?:posted\s+)?(\d+)\s+(minute|hour)s?\s+ago',
                         (job.posted_text or '').strip(), re.I)
    if not match or job.last_verified_at is None:
        return False
    verified = job.last_verified_at
    if verified.tzinfo is None:
        verified = verified.replace(tzinfo=timezone.utc)
    elapsed = reference - verified
    if elapsed < timedelta(0):
        return False
    unit = timedelta(minutes=1) if match[2].lower() == 'minute' else timedelta(hours=1)
    return unit * (int(match[1]) + 1) + elapsed <= timedelta(hours=24)
