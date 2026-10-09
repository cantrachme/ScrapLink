"""Live transport policies and parsing, without contacting any platform."""
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from backend.app.schemas.job import JobListing, JobSearchRequest, JobSource
from backend.app.workers.live_browser import LiveBrowserCollector, careerhub_job


@pytest.mark.parametrize("keyword", ["DevOps Engineer", "Data Scientist", "Product Manager"])
@pytest.mark.parametrize("source", ["linkedin", "wellfound", "careerhub"])
def test_arbitrary_keywords_are_preserved(keyword, source):
    request = JobSearchRequest(keyword=keyword, source=source)
    assert request.keyword == keyword


@pytest.mark.parametrize("delay", [0, 1.4, 3.1, float('nan'), float('inf')])
def test_watch_delay_bounds(delay):
    with pytest.raises(ValidationError):
        JobSearchRequest(keyword="DevOps Engineer", watch_delay_seconds=delay)


def test_title_and_url_suffice_and_description_is_optional():
    job = careerhub_job('<h1>Data Scientist</h1>', 'https://careerhub.za-worknow.com/jobs/data-scientist')
    assert job.title == 'Data Scientist' and job.company == ''
    assert job.description is None and job.location is None
    assert JobListing(source='linkedin', title='DevOps Engineer', job_url='https://www.linkedin.com/jobs/view/12/').company == ''


@pytest.mark.parametrize("source", [JobSource.LINKEDIN, JobSource.WELLFOUND])
def test_restricted_sources_open_browser_but_never_start_automation(source):
    browser = Mock()
    session = Mock(side_effect=AssertionError('Must never collect restricted source'))
    progress = Mock()
    collector = LiveBrowserCollector(session_factory=session, browser_opener=browser)
    result = collector.collect_with_progress(source, JobSearchRequest(source=source.value, keyword='Product Manager'), progress)
    browser.assert_called_once()
    session.assert_not_called()
    assert result.jobs == []
    progress.assert_called_once_with('browser_action', {'action': 'manual_required'})


def test_scrapling_callback_failures_are_not_swallowed(monkeypatch):
    @contextmanager
    def session(**kwargs):
        def fetch(url, **options):
            options['page_action'](object())
            return SimpleNamespace(status=200)
        yield SimpleNamespace(fetch=fetch)
    collector = LiveBrowserCollector(session_factory=session)
    monkeypatch.setattr(collector, '_collect', Mock(side_effect=RuntimeError('source blocked')))
    with pytest.raises(RuntimeError, match='source blocked'):
        collector(JobSource.CAREERHUB, JobSearchRequest(source='careerhub', keyword='Data Scientist'))


import os
from urllib.parse import parse_qs, urlsplit
from scrapling.fetchers import DynamicSession


@pytest.mark.browser
@pytest.mark.skipif(os.environ.get('SCRAPLINK_BROWSER_TESTS') != '1', reason='Opt-in isolated browser test')
def test_real_ui_search_types_submits_clicks_and_extracts_without_platform_traffic():
    seen = []
    @contextmanager
    def session(**options):
        with DynamicSession(**options, extra_flags=['--disable-background-networking', '--host-resolver-rules=MAP * ~NOTFOUND']) as browser:
            def route(request):
                url = urlsplit(request.request.url)
                seen.append(url)
                if url.hostname != 'careerhub.za-worknow.com':
                    request.abort()
                elif url.path == '/jobs/devops':
                    request.fulfill(body='<h1>DevOps Engineer</h1><div class="detail-copy">Deploy services.</div>', content_type='text/html')
                else:
                    keyword = parse_qs(url.query).get('q', [''])[0]
                    cards = '<h3 class="job-row__title"><a href="/jobs/devops">DevOps Engineer</a></h3>' if keyword == 'DevOps Engineer' else ''
                    request.fulfill(body=f'<form class="filter-bar"><label>Search<input type="search" name="q"></label><button>Apply filters</button></form><div class="job-list">{cards}</div>', content_type='text/html')
            browser.context.route('**/*', route)
            yield browser
    log = []
    result = LiveBrowserCollector(headless=True, session_factory=session).collect_with_progress(
        JobSource.CAREERHUB,
        JobSearchRequest(source='careerhub', keyword='DevOps Engineer', location='', date_posted='any', max_results=1, watch_mode=False),
        lambda name, payload: log.append((name, payload)),
    )
    assert result.jobs[0].title == 'DevOps Engineer'
    assert result.jobs[0].company == ''
    assert result.jobs[0].description == 'Deploy services.'
    assert any(parse_qs(url.query).get('q') == ['DevOps Engineer'] for url in seen)
    actions = [payload['action'] for name, payload in log if name == 'browser_action']
    assert actions.index('typed_keyword') < actions.index('submitted_search') < actions.index('opened_listing')
