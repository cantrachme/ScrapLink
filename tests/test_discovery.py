"""Fixed discovery policy plus real PostgreSQL transaction/API/worker tests."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from scrapling.parser import Selector
from sqlalchemy import delete, func, select

from backend.app.api.routes import jobs as routes
from backend.app.database import SessionLocal
from backend.app.main import app
from backend.app.models.job import Job
from backend.app.models.search import SearchTaskRecord, SearchTaskJob
from backend.app.models.search_event import SearchEvent
from backend.app.schemas.job import JobListing, JobSource
from backend.app.sources.discovery import PublicCollector, fresh, publication
from backend.app.workers.queue_worker import JobQueueWorker
from backend.app.workers.execution_lock import execution_lock
from backend.app.workers.run_worker import WORKER_ID

NOW = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize('offset,expected', [(0, True), (7*86400, True), (7*86400+1, False), (-1, False)])
def test_rolling_window_exact_boundaries(offset, expected):
    assert fresh(None, NOW - timedelta(seconds=offset), NOW) is expected


def test_no_modified_or_discovery_date_fallback():
    assert not fresh(None, None, NOW)
    assert publication('yesterday') == (None, None)
    assert publication('invalid') == (None, None)
    assert publication('2026-10-12T08:00:00')[1] is None
    assert not fresh(NOW.date(), None, NOW)
    assert not fresh((NOW-timedelta(days=7)).date(), None, NOW)
    assert fresh((NOW-timedelta(days=3)).date(), None, NOW)
    assert publication('2026-10-12T10:00:00+02:00')[1].hour == 8


class Response:
    def __init__(self, data): self.data = data
    def json(self): return self.data


def test_scan_beyond_twenty_and_per_source_limit(monkeypatch):
    from backend.app.config import settings
    monkeypatch.setattr(settings, 'GREENHOUSE_BOARDS', ['anthropic'])
    rows = [{'id': i, 'first_published': None, 'updated_at': NOW.isoformat()} for i in range(25)]
    rows += [{'id': i, 'first_published': (NOW-timedelta(days=1)).isoformat(),
              'absolute_url': f'https://job-boards.greenhouse.io/anthropic/jobs/{i}'} for i in range(25, 55)]
    # Force unknown dates to be scanned before qualifying ones, independent of source sort order.
    for row in rows[:25]: row['first_published'] = 'unverified'
    collector = PublicCollector()
    calls = []
    def fetch(url, **kwargs):
        calls.append(url)
        if 'boards-api' in url: return Response({'jobs': rows})
        return Selector(content='<div class="job__title"><h1>Real structure</h1></div><div class="job__description">Complete description</div>')
    monkeypatch.setattr(collector, 'fetch', fetch)
    saved, reports = [], []
    collector.collect('greenhouse', NOW, saved.append, lambda state, stats: reports.append((state, stats)))
    assert len(saved) == 20
    assert collector.scanned == 45
    assert collector.undated == 25
    assert reports[-1][0] == 'limit_reached'
    assert all(job.posted_at == NOW-timedelta(days=1) for job in saved)
    assert len([u for u in calls if 'job-boards' in u]) == 20


def test_collector_duplicate_identity_and_missing_fields():
    c = PublicCollector(); c.now = NOW; c.saved = c.scanned = c.undated = 0; c.seen = set()
    output = []; c.save = output.append; c.report = lambda *args: None
    job = sample('ashby')
    c.emit(job); c.emit(job)
    assert len(output) == 1
    assert output[0].location is None and output[0].compensation is None


def sample(source, **overrides):
    values = dict(source=JobSource(source), source_job_id='test-'+source, job_url=f'https://example.com/{source}',
                  title='Test posting', description='Full test-only description', posted_at=NOW-timedelta(days=1),
                  posted_date=(NOW-timedelta(days=1)).date())
    return JobListing(**(values | overrides))


@pytest.fixture
def clean_discovery(monkeypatch):
    monkeypatch.setattr(routes, 'worker_available', lambda db: True)
    yield
    with SessionLocal.begin() as db:
        db.execute(delete(SearchTaskRecord).where(SearchTaskRecord.request_payload['mode'].as_string() == 'discovery'))
        db.execute(delete(Job).where(Job.source_job_id.like('test-%')))


def create_run():
    response = TestClient(app).post('/api/v1/jobs/search')
    assert response.status_code == 202
    from uuid import UUID
    sid = UUID(response.json()['search_id'])
    with SessionLocal.begin() as db:
        db.get(SearchTaskRecord, sid).request_payload = {'mode': 'discovery', 'window_end': NOW.isoformat()}
    return sid


class Collector:
    def stats(self): return {'scanned': 2, 'saved': 1, 'undated': 0}
    def collect(self, source, now, save, report):
        report('collecting', self.stats())
        if source == 'greenhouse': raise RuntimeError('HTTP 403 at public source')
        if source == 'lever':
            report('completed', {'scanned': 50, 'saved': 0, 'undated': 50}); return
        save(sample(source))
        # Independently committed rows and job_saved event must be visible BEFORE collection returns.
        with SessionLocal() as db:
            assert db.scalar(select(Job).where(Job.source_job_id == 'test-'+source)) is not None
            assert db.scalar(select(func.count()).select_from(SearchEvent).where(SearchEvent.event_type == 'job_saved')) > 0
        save(sample(source, job_url=f'https://example.com/alias/{source}'))
        report('completed', self.stats())


def test_incremental_persistence_failures_dedup_sse_and_refresh(clean_discovery):
    sid = create_run()
    assert JobQueueWorker(Collector()).run_once(sid)
    client = TestClient(app)
    data = client.get('/api/v1/jobs').json()
    assert data['run']['status'] == 'completed'
    assert data['run']['saved'] == 2
    assert len(data['jobs']) == 2
    assert data['run']['sources']['greenhouse']['error'].endswith('HTTP 403 at public source')
    assert data['run']['sources']['lever']['saved'] == 0
    assert data['run']['sources']['usajobs']['status'] == 'disabled'
    assert data == client.get('/api/v1/jobs').json()
    wire = client.get(f'/api/v1/jobs/search/{sid}/events')
    assert wire.status_code == 200
    assert wire.text.count('event: job_saved') == 2
    assert 'event: search_completed' in wire.text
    assert all('/alias/' not in j['job_url'] for j in data['jobs'])
    second = create_run()
    JobQueueWorker(Collector()).run_once(second)
    assert len(client.get('/api/v1/jobs').json()['jobs']) == 2


def test_concurrent_start_reuses_single_run(clean_discovery):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: TestClient(app).post('/api/v1/jobs/search').json(), range(4)))
    assert len({r['search_id'] for r in results}) == 1
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(SearchTaskRecord).where(routes.DISCOVERY)) == 1


def test_worker_missing_is_explicit_503(clean_discovery, monkeypatch):
    monkeypatch.setattr(routes, 'worker_available', lambda db: False)
    r = TestClient(app).post('/api/v1/jobs/search')
    assert r.status_code == 503 and 'worker is not running' in r.json()['detail']


def test_worker_liveness_lock():
    with SessionLocal.begin() as db:
        assert not routes.worker_available(db)
    with execution_lock(WORKER_ID):
        with SessionLocal.begin() as db:
            assert routes.worker_available(db)


def test_job_and_event_rollback_together(clean_discovery, monkeypatch):
    sid = create_run()
    from backend.app.repositories.search_event_repository import SearchEventRepository
    publish = SearchEventRepository.publish
    def fail(db, search_id, event, payload):
        if event == 'job_saved': raise RuntimeError('event insert failed')
        return publish(db, search_id, event, payload)
    monkeypatch.setattr(SearchEventRepository, 'publish', staticmethod(fail))
    JobQueueWorker(Collector()).run_once(sid)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(SearchTaskJob).where(SearchTaskJob.search_id == sid)) == 0
        assert db.scalar(select(Job).where(Job.source_job_id == 'test-ashby')) is None


def test_worker_defends_freshness_and_limit(clean_discovery):
    class Excess(Collector):
        def collect(self, source, now, save, report):
            if source != 'ashby': return
            for i in range(21):
                save(sample(source, source_job_id=f'test-{i}', job_url=f'https://example.com/{i}'))
    sid = create_run(); JobQueueWorker(Excess()).run_once(sid)
    data = TestClient(app).get('/api/v1/jobs').json()
    assert data['run']['saved'] == 20
    assert 'limit exceeded' in data['run']['sources']['ashby']['error']


def test_stale_recovery_retains_progress(clean_discovery):
    sid = create_run()
    with SessionLocal.begin() as db:
        task = db.get(SearchTaskRecord, sid); task.status = 'running'; task.updated_at = NOW-timedelta(days=1)
    worker = JobQueueWorker(Collector())
    assert worker.recover_stale(1, search_id=sid) == 1
    assert worker.recover_stale(1, search_id=sid) == 0
    assert TestClient(app).get('/api/v1/jobs').json()['run']['status'] == 'failed'


def test_salary_does_not_turn_benefits_into_pay():
    from backend.app.sources.discovery import salary_text, ashby_salary
    assert salary_text('$100/month education budget\n$250 tool budget') is None
    assert salary_text('The base salary is $100,000 per year').raw_text == 'The base salary is $100,000 per year'
    assert ashby_salary({'compensation': {'compensationTiers': [
        {'title': 'UK', 'tierSummary': '£100–£200'}, {'title': 'EU', 'tierSummary': '€150–€250'}]}}).raw_text == 'UK: £100–£200\nEU: €150–€250'


def test_blocked_request_has_source_and_status_without_retry(monkeypatch):
    from backend.app.sources import discovery
    from types import SimpleNamespace
    import time
    calls = []
    def get(url, **kwargs):
        calls.append((url, kwargs)); return SimpleNamespace(status=403)
    monkeypatch.setattr(discovery.Fetcher, 'get', get)
    c = PublicCollector(); c.deadline = time.monotonic()+30
    with pytest.raises(RuntimeError, match='HTTP 403 at jobs.lever.co/palantir'):
        c.fetch('https://jobs.lever.co/palantir')
    assert len(calls) == 1 and calls[0][1]['retries'] == 0


def test_ashby_html_identity_and_repost_date(monkeypatch):
    from backend.app.config import settings
    import json
    monkeypatch.setattr(settings, 'ASHBY_BOARDS', ['ashby'])
    row = {'id': '123', 'isListed': True, 'publishedAt': (NOW-timedelta(days=1)).isoformat(),
           'jobUrl': 'https://jobs.ashbyhq.com/ashby/123'}
    data = {'@type': 'JobPosting', 'identifier': {'value': '123'}, 'datePosted': '2020-01-01',
            'title': 'Old role', 'description': '<p>Complete</p>'}
    c = PublicCollector()
    monkeypatch.setattr(c, 'fetch', lambda url, **kwargs: Response({'jobs': [row]}) if 'api.ashby' in url else Selector(content='<script type="application/ld+json">'+json.dumps(data)+'</script>'))
    jobs=[];c.collect('ashby',NOW,jobs.append,lambda *args:None)
    assert jobs == []
    data['datePosted']='2026-10-13';data['identifier']['value']='wrong'
    with pytest.raises(ValueError, match='identity'):
        c.collect('ashby',NOW,jobs.append,lambda *args:None)


def test_usajobs_requests_full_fields_and_preserves_publication(monkeypatch):
    c = PublicCollector(); calls=[]; jobs=[]
    item = {'MatchedObjectId': '1', 'MatchedObjectDescriptor': {
        'PositionURI': 'https://www.usajobs.gov/GetJob/ViewDetails/1', 'PositionTitle': 'Test-only role',
        'PublicationStartDate': '2026-10-12T10:00:00Z', 'OrganizationName': 'Test agency',
        'QualificationSummary': 'Qualification evidence', 'PositionSchedule': [{'Name':'Full Time'}],
        'PositionRemuneration': [{'MinimumRange':'100', 'MaximumRange':'200', 'RateIntervalCode':'PA'}],
        'UserArea': {'Details': {'MajorDuties':['First duty', 'Second duty'], 'Benefits':'Published benefits'}}}}
    def fetch(url, **kwargs):
        calls.append(url)
        return Response({'SearchResult': {'SearchResultItems': [item] if len(calls)==1 else []}})
    monkeypatch.setattr(c,'fetch',fetch)
    c.collect('usajobs',NOW,jobs.append,lambda *args:None)
    assert 'Fields=Full' in calls[0] and 'Keyword' not in calls[0]
    assert jobs[0].posted_at == datetime(2026,10,12,10,tzinfo=timezone.utc)
    assert 'First duty' in jobs[0].description and 'Qualification evidence' in jobs[0].description
    assert jobs[0].employment_type.value == 'full_time'


def test_remotive_cache_avoids_repeated_requests(monkeypatch, tmp_path):
    from backend.app.config import settings
    import json
    cache=tmp_path/'remotive.json'
    cache.write_text(json.dumps({'jobs': [{'id': 1, 'url': 'https://remotive.com/remote-jobs/test/1',
        'title': 'Isolated test posting', 'company_name': 'Test', 'publication_date': '2026-10-11T12:00:00',
        'description': '<p>Test description</p>'}]}))
    monkeypatch.setattr(settings, 'REMOTIVE_CACHE_PATH', str(cache))
    c=PublicCollector(); saved=[]
    monkeypatch.setattr(c, 'fetch', lambda *args, **kwargs: pytest.fail('Fresh cache must avoid API request'))
    c.collect('remotive', NOW, saved.append, lambda *args: None)
    assert len(saved)==1 and saved[0].posted_at is None
    assert 'timezone unspecified' in saved[0].posted_text
