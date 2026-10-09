"""Active Jobs contracts, policy gates and PostgreSQL streaming; no platform traffic."""
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from backend.app.config import settings
from backend.app.database import SessionLocal
from backend.app.main import app
from backend.app.models.job import Job
from backend.app.models.search import SearchTaskRecord, SearchTaskJob
from backend.app.repositories.search_event_repository import SearchEventRepository as Events
from backend.app.repositories.search_repository import SearchRepository as Searches
from backend.app.schemas.job import JobListing, JobSearchRequest, JobSource, JobStatus
from backend.app.services.job_pipeline import PipelineResult
from backend.app.workers.active_browser import discovery_url
from backend.app.workers.active_jobs import SourceUnavailable
from backend.app.workers.live_browser import LiveBrowserCollector
from backend.app.workers.queue_worker import JobQueueWorker

client = TestClient(app)


@pytest.fixture
def active_search():
    ids = []
    def create(max_results=50):
        response = client.post('/api/v1/jobs/active', json={'max_results': max_results})
        assert response.status_code == 202, response.text
        sid = UUID(response.json()['search_id'])
        ids.append(sid)
        return sid
    yield create
    with SessionLocal.begin() as db:
        job_ids = list(db.scalars(select(SearchTaskJob.job_id).where(SearchTaskJob.search_id.in_(ids))))
        db.execute(delete(SearchTaskRecord).where(SearchTaskRecord.search_id.in_(ids)))
        db.execute(delete(Job).where(Job.id.in_(job_ids)))


def listing(source, **changes):
    url = f'https://www.linkedin.com/jobs/view/{uuid4().int}/' if source == JobSource.LINKEDIN else f'https://wellfound.com/jobs/{uuid4().int}'
    return JobListing(source=source, title='Actual supplied title', job_url=url,
                      posted_at=datetime.now(timezone.utc) - timedelta(hours=2), **changes)


def test_active_request_needs_no_keyword_location_and_preserves_old_search_validation(active_search):
    sid = active_search(3)
    task = client.get(f'/api/v1/jobs/search/{sid}').json()
    assert task['request']['mode'] == 'active_jobs'
    assert task['request']['keyword'] == task['request']['location'] == ''
    assert task['request']['date_posted'] == '24h'
    assert task['request']['max_results'] == 3
    assert client.post('/api/v1/jobs/search', json={}).status_code == 422
    for body in ({'keyword': 'Engineer'}, {'location': 'London'}, {'max_results': 0}, {'max_results': 501}, {'watch_delay_seconds': 0}):
        assert client.post('/api/v1/jobs/active', json=body).status_code == 422
    assert discovery_url(JobSource.LINKEDIN).endswith('?sortBy=DD&f_TPR=r86400')
    assert discovery_url(JobSource.WELLFOUND) == 'https://wellfound.com/jobs'


def test_both_unauthorized_sources_open_visible_browser_without_automation(active_search, monkeypatch):
    monkeypatch.setattr(settings, 'ACTIVE_JOBS_AUTHORIZATIONS', {})
    sid = active_search()
    opener, session = Mock(), Mock(side_effect=AssertionError('No permission to automate'))
    assert JobQueueWorker(LiveBrowserCollector(browser_opener=opener, session_factory=session)).run_once(sid)
    assert [call.args[0] for call in opener.call_args_list] == [discovery_url(s) for s in (JobSource.LINKEDIN, JobSource.WELLFOUND)]
    session.assert_not_called()
    results = client.get(f'/api/v1/jobs/search/{sid}/results').json()
    assert results['jobs'] == []
    assert results['source_statuses'] == {'linkedin': 'authorization_required', 'wellfound': 'authorization_required'}
    assert {f['source'] for f in results['failures']} == {'linkedin', 'wellfound'}


@pytest.mark.parametrize('failing_source', [JobSource.LINKEDIN, JobSource.WELLFOUND])
def test_saved_job_is_readable_before_collector_returns_and_other_source_error_is_isolated(active_search, failing_source):
    sid = active_search()
    calls = []
    class Collector:
        def collect_with_progress(self, source, request, progress):
            calls.append(source)
            assert request.keyword == request.location == ''
            if source == failing_source:
                raise SourceUnavailable('access_blocked')
            job = listing(source, company='Supplied Company', description='Full supplied JD', compensation={'raw_text': '$100k'})
            progress('job_collected', {'job': job})
            # Independent HTTP/session reads see the job while the browser is
            # still collecting and before any terminal event exists.
            result = client.get(f'/api/v1/jobs/search/{sid}/results').json()
            assert result['status'] == 'running'
            assert result['jobs'][0]['description'] == 'Full supplied JD'
            assert result['jobs'][0]['compensation']['raw_text'] == '$100k'
            with SessionLocal() as db:
                events = Events.get_after(db, sid, 0)
                assert events[-1].event_type == 'job_saved'
                assert events[-1].payload['job_id'] == result['jobs'][0]['id']
                assert all(e.event_type != 'search_completed' for e in events)
            progress('job_collected', {'job': job.model_copy(update={'job_url': job.job_url + '?tracking=ignored'})})
            return PipelineResult(source=source, jobs=[job])
    assert JobQueueWorker(Collector()).run_once(sid)
    assert calls == [JobSource.LINKEDIN, JobSource.WELLFOUND]
    results = client.get(f'/api/v1/jobs/search/{sid}/results').json()
    assert results['status'] == 'completed'
    assert len(results['jobs']) == results['total_extracted'] == 1
    assert results['source_statuses'][failing_source.value] == 'access_blocked'
    assert results['source_statuses']['wellfound' if failing_source == JobSource.LINKEDIN else 'linkedin'] == 'completed'
    assert results['jobs'][0]['status'] == 'unknown'
    assert results['jobs'][0]['location'] is None


def test_posting_evidence_global_cap_and_source_sorting(active_search):
    sid = active_search(2)
    class Collector:
        def collect_with_progress(self, source, request, progress):
            recent = listing(source)
            if source == JobSource.LINKEDIN:
                for changes in ({'posted_at': None}, {'posted_at': datetime.now(timezone.utc) - timedelta(days=5)},
                                {'posted_at': datetime.now(timezone.utc) + timedelta(hours=1)}, {'status': 'closed'}):
                    progress('job_collected', {'job': recent.model_copy(update=changes)})
                with SessionLocal() as db:
                    assert Searches.get_results(db, sid).jobs == []
            else:
                recent.posted_at = datetime.now(timezone.utc) - timedelta(minutes=10)
            progress('job_collected', {'job': recent})
            return PipelineResult(source=source, jobs=[recent])
    assert JobQueueWorker(Collector()).run_once(sid)
    result = client.get(f'/api/v1/jobs/search/{sid}/results').json()
    assert result['total_extracted'] == 2
    assert [j['source'] for j in result['jobs']] == ['wellfound', 'linkedin']
    assert result['source'] is None
    assert all(j['company'] == '' for j in result['jobs'])


def test_save_event_failure_rolls_back_only_current_job(active_search, monkeypatch):
    sid = active_search()
    class Collector:
        def collect_with_progress(self, source, request, progress):
            progress('job_collected', {'job': listing(source)})
            progress('job_collected', {'job': listing(source)})
            pytest.fail('Persistence failure must stop the collector')
    worker = JobQueueWorker(Collector())
    publish = worker.events.publish
    saved_events = 0
    def broken(db, search_id, name, payload):
        nonlocal saved_events
        event = publish(db, search_id, name, payload)
        if name == 'job_saved':
            saved_events += 1
            if saved_events == 2:
                raise RuntimeError('Test event failure')
        return event
    monkeypatch.setattr(worker.events, 'publish', broken)
    assert worker.run_once(sid)
    result = client.get(f'/api/v1/jobs/search/{sid}/results').json()
    assert result['status'] == 'failed'
    assert len(result['jobs']) == result['total_extracted'] == 1


def test_assisted_jobs_accept_both_sources_complete_details_and_share_cap(active_search, monkeypatch):
    monkeypatch.setattr(settings, 'ACTIVE_JOBS_AUTHORIZATIONS', {})
    sid = active_search(2)
    JobQueueWorker(LiveBrowserCollector(browser_opener=lambda url: None)).run_once(sid)
    url = f'/api/v1/jobs/search/{sid}/assisted-jobs'
    first = listing(JobSource.LINKEDIN)
    body = {'source': 'linkedin', 'title': first.title, 'job_url': first.job_url, 'company': 'Company',
            'description': 'Complete user-supplied JD', 'compensation': {'raw_text': 'Published salary'},
            'posted_text': '2 hours ago', 'posted_date': '2026-10-09'}
    response = client.post(url, json=body)
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'unknown'
    assert response.json()['last_verified_at'] is None
    assert client.post(url, json=body).json()['id'] == response.json()['id']
    second = listing(JobSource.WELLFOUND)
    body2 = {'source': 'wellfound', 'title': second.title, 'job_url': second.job_url}
    assert client.post(url, json=body2).status_code == 200
    assert client.post(url, json={**body2, 'job_url': listing(JobSource.WELLFOUND).job_url}).status_code == 409
    assert client.post(url, json={**body2, 'source': 'linkedin'}).status_code == 422
    with SessionLocal() as db:
        assert [e.event_type for e in Events.get_after(db, sid, 0)][-1] == 'job_saved'


def test_relative_date_evidence_preserved_without_invented_timestamp_and_expiry():
    from scrapling.parser import Selector
    from backend.app.services.active_job_details import enrich_active_details, matches_active_posting_window
    now = datetime.now(timezone.utc)
    job = listing(JobSource.LINKEDIN).model_copy(update={'posted_at': None})
    enrich_active_details(job, Selector(content='<span class="posted-time-ago__text">2 hours ago</span><span class="compensation__salary">$100k</span><span data-testid="workplace-type">On-site</span>'), {}, now)
    assert job.posted_at is None and job.posted_date is None
    assert job.posted_text == '2 hours ago'
    assert job.compensation.raw_text == '$100k'
    assert job.workplace_type.value == 'onsite'
    assert matches_active_posting_window(job, now)
    for text in ('24 hours ago', 'reposted 2 hours ago', 'recently', '1 day ago', ''):
        assert not matches_active_posting_window(job.model_copy(update={'posted_text': text}), now)
    enrich_active_details(job, Selector(content='<h1>Expired job</h1>'), {'validThrough': (now - timedelta(days=1)).isoformat()}, now)
    assert job.status == 'closed'
    assert not matches_active_posting_window(job, now)


def test_follow_stream_delivers_assisted_saves_after_completion(active_search, monkeypatch):
    import asyncio
    from backend.app.services.search_event_stream import stream_search_events
    from backend.app.services import search_event_stream as streaming
    sid = active_search()
    monkeypatch.setattr(settings, 'ACTIVE_JOBS_AUTHORIZATIONS', {})
    JobQueueWorker(LiveBrowserCollector(browser_opener=lambda url: None)).run_once(sid)
    monkeypatch.setattr(streaming, 'POLL_INTERVAL_SECONDS', 0.001)
    class Request:
        async def is_disconnected(self):
            return False
    async def check():
        stream = stream_search_events(Request(), sid, 0, follow=True)
        async with asyncio.timeout(3):
            async for frame in stream:
                if 'event: search_completed' in frame:
                    job = listing(JobSource.WELLFOUND)
                    response = client.post(f'/api/v1/jobs/search/{sid}/assisted-jobs',
                        json={'source': 'wellfound', 'title': job.title, 'job_url': job.job_url})
                    assert response.status_code == 200
                elif 'event: job_saved' in frame:
                    break
        await stream.aclose()
    asyncio.run(check())


import os
from contextlib import contextmanager
from urllib.parse import urlsplit
import json
from scrapling.fetchers import DynamicSession


@pytest.mark.browser
@pytest.mark.skipif(os.environ.get('SCRAPLINK_BROWSER_TESTS') != '1', reason='Opt-in isolated visible Chrome test')
def test_visible_chrome_multisource_discovery_and_incremental_database_saves(active_search, monkeypatch):
    monkeypatch.setattr(settings, 'ACTIVE_JOBS_AUTHORIZATIONS', {'linkedin': 'isolated fixture permission', 'wellfound': 'isolated fixture permission'})
    sid = active_search(4)
    visited = []
    @contextmanager
    def session(**options):
        assert options['headless'] is False and options['real_chrome'] is True
        with DynamicSession(**options, extra_flags=['--disable-background-networking', '--host-resolver-rules=MAP * ~NOTFOUND']) as browser:
            def route_handler(route):
                target = urlsplit(route.request.url)
                if target.hostname not in ('www.linkedin.com', 'wellfound.com'):
                    route.abort()
                    return
                visited.append(target)
                source = 'linkedin' if target.hostname == 'www.linkedin.com' else 'wellfound'
                base = '/jobs/view/' if source == 'linkedin' else '/jobs/'
                if target.path in ('/jobs/search/', '/jobs'):
                    markup = ''.join(f'<a href="https://{target.hostname}{base}{number}">Listing {number}</a>' for number in (1001, 1002))
                    route.fulfill(body=f'<html><head><title>Jobs</title></head><body>{markup}</body></html>', content_type='text/html')
                else:
                    data = {'@type': 'JobPosting', 'title': f'{source} supplied role', 'hiringOrganization': {'name': 'Fixture only'},
                            'datePosted': (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
                            'description': '<p>Entire fixture job description.</p>', 'jobLocationType': 'TELECOMMUTE',
                            'baseSalary': {'currency': 'USD', 'value': {'minValue': 100000, 'maxValue': 120000, 'unitText': 'YEAR'}}}
                    route.fulfill(body=f'<html><head><title>Job details</title><script type="application/ld+json">{json.dumps(data)}</script></head><body><h1>{data["title"]}</h1></body></html>', content_type='text/html')
            browser.context.route('**/*', route_handler)
            yield browser
    collector = LiveBrowserCollector(session_factory=session)
    original = collector.collect_with_progress
    observed = []
    def collect(source, request, progress):
        def inspect(name, payload):
            progress(name, payload)
            if name == 'job_collected':
                with SessionLocal() as db:
                    results = Searches.get_results(db, sid)
                    assert results.status == 'running'
                    observed.append(results.total_extracted)
        return original(source, request, inspect)
    monkeypatch.setattr(collector, 'collect_with_progress', collect)
    assert JobQueueWorker(collector).run_once(sid)
    with SessionLocal() as db:
        results = Searches.get_results(db, sid)
        assert results.source_statuses == {'linkedin': 'completed', 'wellfound': 'completed'}
        assert len(results.jobs) == 4
        assert all(j.description == 'Entire fixture job description.' and j.workplace_type == 'remote' for j in results.jobs)
    assert observed == [1, 2, 3, 4]
    assert {v.hostname for v in visited} == {'www.linkedin.com', 'wellfound.com'}
    assert not any('keywords=' in v.query or 'location=' in v.query for v in visited)


def test_authorized_collector_stops_at_challenge_without_inspection(monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace
    monkeypatch.setattr(settings, 'ACTIVE_JOBS_AUTHORIZATIONS', {'linkedin': 'test permission'})
    @contextmanager
    def session(**options):
        page = Mock()
        page.url = discovery_url(JobSource.LINKEDIN)
        page.locator.return_value.count.return_value = 1
        def fetch(url, **kwargs):
            kwargs['page_action'](page)
            page.goto.assert_not_called()
            page.content.assert_not_called()
            return SimpleNamespace(status=200)
        yield SimpleNamespace(fetch=fetch)
    progress = Mock()
    with pytest.raises(SourceUnavailable) as error:
        LiveBrowserCollector(session_factory=session).collect_with_progress(JobSource.LINKEDIN,
            JobSearchRequest(mode='active_jobs', keyword='', location=''), progress)
    assert error.value.status == 'access_blocked'
    progress.assert_not_called()


def test_fresh_inspection_without_availability_evidence_does_not_inherit_active_badge(active_search):
    from backend.app.repositories.job_repository import JobRepository
    sid = active_search()
    job = listing(JobSource.LINKEDIN)
    with SessionLocal.begin() as db:
        JobRepository.upsert(db, job.model_copy(update={'status': JobStatus.ACTIVE}))
    class Collector:
        def collect_with_progress(self, source, request, progress):
            if source == JobSource.LINKEDIN:
                progress('job_collected', {'job': job})
            return PipelineResult(source=source)
    assert JobQueueWorker(Collector()).run_once(sid)
    with SessionLocal() as db:
        assert Searches.get_results(db, sid).jobs[0].status == 'unknown'
