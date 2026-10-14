"""Bounded public-source discovery. HTML is required for employer job details."""
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from scrapling.fetchers import Fetcher
from scrapling.parser import Selector

from backend.app.config import settings
from backend.app.schemas.job import Compensation, JobListing, JobSource
from backend.app.sources.structured_job import employment_type, workplace_type

logger = logging.getLogger(__name__)
UTC = timezone.utc
LIMIT = 20
MAX_METADATA = 1000
MAX_DETAILS = 120
SOURCE_SECONDS = 180


def publication(value):
    """Retain uncertainty: never assign a timezone or midnight to source dates."""
    if not isinstance(value, str) or not re.match(r'^\d{4}-\d{2}-\d{2}(?:$|T)', value):
        return None, None
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None, None
    return dt.date(), dt.astimezone(UTC) if dt.tzinfo else None


def fresh(posted_date, posted_at, now):
    if posted_at is not None:
        return posted_at.tzinfo is not None and now - timedelta(days=7) <= posted_at <= now
    if posted_date is None:
        return False
    # Date-only/unspecified-zone values qualify only if the entire possible
    # calendar day (across UTC-12 .. UTC+14) fits inside the rolling window.
    midnight = datetime.combine(posted_date, datetime.min.time(), UTC)
    return now - timedelta(days=7) <= midnight - timedelta(hours=14) and midnight + timedelta(hours=36) <= now


def text_html(html):
    return Selector(content=html).get_all_text(separator='\n', strip=True) if html else None


def node_text(page, selector):
    nodes = page.css(selector)
    return nodes[0].get_all_text(separator='\n', strip=True) if nodes else None


def structured(page):
    def walk(value):
        if isinstance(value, list):
            for item in value:
                yield from walk(item)
        elif isinstance(value, dict):
            if value.get('@type') == 'JobPosting':
                yield value
            yield from walk(value.get('@graph', []))
    for raw in page.css('script[type="application/ld+json"]::text').getall():
        try:
            yield from walk(json.loads(raw))
        except (ValueError, TypeError):
            continue


def salary_text(description):
    # Only explicit pay statements, never infer pay from equipment/education budgets.
    lines = [line for line in (description or '').splitlines()
             if re.search(r'\b(?:salary|compensation|pay range|base pay|earnings|OTE)\b', line, re.I)
             and re.search(r'[$£€]\s*[\d,]+|\b(?:USD|GBP|EUR)\s*[\d,]+', line)]
    return Compensation(raw_text='\n'.join(lines)) if lines else None


def ashby_salary(row):
    data = row.get('compensation') or {}
    tiers = [f"{tier.get('title', '')}: {tier['tierSummary']}" for tier in data.get('compensationTiers', []) if tier.get('tierSummary')]
    raw = '\n'.join(tiers) or data.get('compensationTierSummary')
    return Compensation(raw_text=raw) if raw else None


def owned_url(url, host, board=None):
    p = urlsplit(url)
    if p.scheme != 'https' or p.hostname != host or p.username or p.password or p.port not in (None, 443):
        raise ValueError('Unexpected original posting URL')
    if board and not p.path.startswith('/' + board + '/'):
        raise ValueError('Posting URL does not belong to the configured employer board')
    return url


class PublicCollector:
    def __init__(self, check_cancelled=lambda: None):
        self.check_cancelled = check_cancelled
        self.robots = {}
        self.last_request = 0.0

    def fetch(self, url, *, html=False, headers=None):
        self.check_cancelled()
        remaining = self.deadline - time.monotonic()
        if remaining <= 1:
            raise TimeoutError('Source time limit reached (180 seconds)')
        if html:
            p = urlsplit(url)
            origin = f'{p.scheme}://{p.netloc}'
            if origin not in self.robots:
                response = self.fetch(origin + '/robots.txt')
                robot = RobotFileParser()
                robot.parse(response.body.decode().splitlines())
                self.robots[origin] = robot
            if not self.robots[origin].can_fetch('ScrapLink', url):
                raise PermissionError('Source robots.txt disallows this posting')
        time.sleep(max(0, 1.0 - (time.monotonic() - self.last_request)))
        self.check_cancelled()
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Source time limit reached (180 seconds)')
        self.last_request = time.monotonic()
        try:
            page = Fetcher.get(url, stealthy_headers=False, retries=0,
                               timeout=min(20, remaining), follow_redirects=False,
                               headers=headers or {'User-Agent': 'ScrapLink/1.0 public job discovery'})
        except Exception as exc:
            # Avoid leaking request headers (USAJOBS credentials) through errors.
            raise RuntimeError(f'Request failed at {urlsplit(url).hostname}: {type(exc).__name__}') from exc
        if page.status != 200:
            raise RuntimeError(f'HTTP {page.status} at {urlsplit(url).hostname}{urlsplit(url).path}; no retry or bypass')
        logger.info('Scrapling retrieved %s', url)
        return page

    def collect(self, source, now, save, report):
        self.deadline = time.monotonic() + SOURCE_SECONDS
        self.scanned = self.saved = self.undated = self.details = 0
        self.seen = set()
        self.now, self.save, self.report = now, save, report
        self.source = source
        report('collecting', self.stats())
        getattr(self, source)()
        limited = self.saved >= LIMIT or self.details >= MAX_DETAILS or self.scanned >= MAX_METADATA
        report('limit_reached' if limited else 'completed', self.stats())

    def stats(self):
        return {'scanned': self.scanned, 'saved': self.saved, 'undated': self.undated}

    def candidate(self, raw):
        self.scanned += 1
        d, dt = publication(raw)
        if d is None:
            self.undated += 1
        if self.scanned % 10 == 0:
            self.report('collecting', self.stats())
        return fresh(d, dt, self.now)

    def emit(self, job):
        key = job.source_job_id or job.job_url
        if key in self.seen or not fresh(job.posted_date, job.posted_at, self.now):
            return
        if not job.title or not job.description:
            raise ValueError('Posting title or full description missing in source HTML')
        self.save(job)
        self.seen.add(key)
        self.saved += 1
        self.report('collecting', self.stats())

    def ashby(self):
        for board in settings.ASHBY_BOARDS:
            rows = self.fetch(f'https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true').json()['jobs']
            for row in sorted(rows, key=lambda j: j.get('publishedAt') or '', reverse=True):
                if self.saved >= LIMIT or self.scanned >= MAX_METADATA or self.details >= MAX_DETAILS:
                    return
                if not row.get('isListed', True) or not self.candidate(row.get('publishedAt')):
                    continue
                url = owned_url(row['jobUrl'], 'jobs.ashbyhq.com', board)
                page = self.fetch(url, html=True)
                self.details += 1
                data = next(structured(page), None)
                if not data or data.get('identifier', {}).get('value') != row['id']:
                    raise ValueError('Ashby HTML posting identity missing or mismatched')
                # publishedAt is last publication; reject an explicitly older original date.
                original, _ = publication(data.get('datePosted'))
                if original and original < (self.now - timedelta(days=7)).date():
                    continue
                d, dt = publication(row.get('publishedAt'))
                description = text_html(data.get('description'))
                self.emit(JobListing(source=JobSource.ASHBY, source_job_id=f'{board}:{row["id"]}',
                    job_url=url, title=data['title'], company=data.get('hiringOrganization', {}).get('name') or '',
                    location=row.get('location'), workplace_type=workplace_type(row.get('workplaceType')),
                    employment_type=employment_type(row.get('employmentType')),
                    compensation=ashby_salary(row), description=description,
                    posted_date=d, posted_at=dt, posted_text=f'publishedAt (last publication): {row["publishedAt"]}',
                    last_verified_at=self.now))

    def greenhouse(self):
        for board in settings.GREENHOUSE_BOARDS:
            rows = self.fetch(f'https://boards-api.greenhouse.io/v1/boards/{board}/jobs').json()['jobs']
            # Missing dates are inspected too, within the detail/time cap. Never use updated_at.
            for row in sorted(rows, key=lambda j: j.get('first_published') or '', reverse=True):
                if self.saved >= LIMIT or self.scanned >= MAX_METADATA or self.details >= MAX_DETAILS:
                    return
                if not row.get('first_published'):
                    row = self.fetch(f'https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{row["id"]}').json()
                    self.details += 1
                if not self.candidate(row.get('first_published')):
                    continue
                deadline_date, deadline_at = publication(row.get('application_deadline'))
                if (deadline_at and deadline_at <= self.now) or (deadline_date and deadline_date < self.now.date()):
                    continue
                url = owned_url(row['absolute_url'], 'job-boards.greenhouse.io', board)
                page = self.fetch(url, html=True)
                self.details += 1
                title, description = node_text(page, '.job__title h1'), node_text(page, '.job__description')
                if not title or not description:
                    raise ValueError('Greenhouse title or description missing from HTML')
                d, dt = publication(row.get('first_published'))
                fields = {m['name'].lower(): m.get('value') for m in row.get('metadata') or []}
                self.emit(JobListing(source=JobSource.GREENHOUSE, source_job_id=f'{board}:{row["id"]}',
                    job_url=url, title=title, company=row.get('company_name') or '',
                    location=node_text(page, '.job__location'), workplace_type=workplace_type(fields.get('location type')),
                    description=description, compensation=(Compensation(raw_text=node_text(page, ".job__pay-ranges"))
                        if node_text(page, ".job__pay-ranges") else salary_text(description)),
                    posted_date=d, posted_at=dt, posted_text=f'first_published: {row["first_published"]}', last_verified_at=self.now))

    def lever(self):
        for board in settings.LEVER_BOARDS:
            page = self.fetch(f'https://jobs.lever.co/{board}', html=True)
            urls = list(dict.fromkeys(page.css('a.posting-title::attr(href)').getall()))
            if not urls and 'no open' not in page.get_all_text().lower():
                raise ValueError('Unrecognized Lever board markup')
            # createdAt is only a scan-order hint, never publication evidence.
            rows = self.fetch(f'https://api.lever.co/v0/postings/{board}?mode=json').json()
            order = {j['hostedUrl']: j.get('createdAt', 0) for j in rows}
            for url in sorted(urls, key=lambda u: order.get(u, 0), reverse=True):
                if self.saved >= LIMIT or self.details >= MAX_DETAILS:
                    return
                page = self.fetch(owned_url(url, 'jobs.lever.co', board), html=True)
                self.details += 1
                data = next(structured(page), {})
                if not self.candidate(data.get('datePosted')):
                    continue
                d, dt = publication(data.get('datePosted'))
                description = node_text(page, '.content .section-wrapper')
                # Lever renders the complete body across sibling posting sections.
                sections = page.css('.section-wrapper .section.page-centered:not(.posting-header):not(.last-section-apply)')
                if sections:
                    description = '\n\n'.join(x.get_all_text(separator='\n', strip=True) for x in sections)
                self.emit(JobListing(source=JobSource.LEVER, source_job_id=f'{board}:{urlsplit(url).path.rsplit("/", 1)[-1]}',
                    job_url=url, title=data['title'], company=data.get('hiringOrganization', {}).get('name') or '',
                    location=node_text(page, '.posting-categories .location'),
                    workplace_type=workplace_type(node_text(page, '.posting-categories .workplaceTypes')),
                    employment_type=employment_type(data.get('employmentType')),
                    description=description, compensation=salary_text(description), posted_date=d, posted_at=dt,
                    posted_text=f'datePosted: {data["datePosted"]}', last_verified_at=self.now))

    def remotive(self):
        # Official redistribution API; six-hour cache respects its four/day advice.
        cache = Path(settings.REMOTIVE_CACHE_PATH)
        if cache.exists() and time.time() - cache.stat().st_mtime < 6 * 3600:
            rows = json.loads(cache.read_text())['jobs']
        else:
            payload = self.fetch('https://remotive.com/api/remote-jobs').json()
            rows = payload['jobs']
            cache.parent.mkdir(parents=True, exist_ok=True)
            temp = cache.with_suffix('.tmp')
            temp.write_text(json.dumps(payload))
            temp.replace(cache)
        for row in rows[:MAX_METADATA]:
            if self.saved >= LIMIT:
                return
            if not self.candidate(row.get('publication_date')):
                continue
            d, dt = publication(row.get('publication_date'))
            self.emit(JobListing(source=JobSource.REMOTIVE, source_job_id=str(row['id']),
                job_url=owned_url(row['url'], 'remotive.com'), title=row['title'], company=row.get('company_name') or '',
                location=row.get('candidate_required_location'), workplace_type='remote',
                employment_type=employment_type(row.get('job_type')), description=text_html(row.get('description')),
                compensation=Compensation(raw_text=row['salary']) if row.get('salary') else None,
                posted_date=d, posted_at=dt, posted_text=f'publication_date (source timezone unspecified): {row["publication_date"]}',
                last_verified_at=self.now))

    def usajobs(self):
        headers = {'User-Agent': settings.USAJOBS_EMAIL, 'Authorization-Key': settings.USAJOBS_API_KEY}
        for number in range(1, 6):
            data = self.fetch(f'https://data.usajobs.gov/api/search?Fields=Full&DatePosted=7&ResultsPerPage=100&Page={number}', headers=headers).json()['SearchResult']
            items = data.get('SearchResultItems', [])
            if not items:
                return
            for item in items:
                if self.saved >= LIMIT:
                    return
                row = item['MatchedObjectDescriptor']
                if not self.candidate(row.get('PublicationStartDate')):
                    continue
                d, dt = publication(row.get('PublicationStartDate'))
                remuneration = row.get('PositionRemuneration') or []
                pay = '\n'.join(' '.join(str(r[k]) for k in ('MinimumRange', 'MaximumRange', 'RateIntervalCode') if r.get(k)) for r in remuneration)
                schedule = row.get('PositionSchedule') or []
                details = row.get('UserArea', {}).get('Details', {})
                description_parts = [row.get('QualificationSummary') or '']
                for key in ('JobSummary', 'MajorDuties', 'Requirements', 'Education', 'Evaluations',
                            'OtherInformation', 'Benefits', 'HowToApply', 'RequiredDocuments', 'WhatToExpectNext'):
                    value = details.get(key)
                    if isinstance(value, list):
                        value = '\n'.join(str(part) for part in value)
                    if value:
                        description_parts.append(f'{key}:\n{value}')
                self.emit(JobListing(source=JobSource.USAJOBS, source_job_id=item['MatchedObjectId'],
                    job_url=owned_url(row['PositionURI'], 'www.usajobs.gov'), title=row['PositionTitle'],
                    company=row.get('OrganizationName') or '', location=row.get('PositionLocationDisplay'),
                    employment_type=employment_type(schedule[0].get('Name')) if schedule else None,
                    compensation=Compensation(raw_text=pay) if pay else None,
                    description=text_html('\n\n'.join(description_parts)),
                    posted_date=d, posted_at=dt, posted_text=f'PublicationStartDate: {row["PublicationStartDate"]}', last_verified_at=self.now))
