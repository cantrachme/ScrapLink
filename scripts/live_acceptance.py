"""Real browser acceptance through Nginx at http://localhost:8000 only.
Requires docker compose build && docker compose up. No direct database access.
This opt-in test performs real collection and writes evidence under /tmp.
"""
import json
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.sources.discovery import fresh

ORIGIN = 'http://localhost:8000'


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1280, 'height': 900})
        errors, requests = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: requests.append(request.url))
        # Observe native SSE before React initializes; do not mock network traffic.
        page.add_init_script('''
            window.__sse = [];
            const Native = window.EventSource;
            window.EventSource = class extends Native {
                constructor(url) { super(url);
                    for (const name of ['job_saved', 'search_completed', 'source_status'])
                        this.addEventListener(name, e => window.__sse.push({
                            type: name, data: JSON.parse(e.data), url, at: Date.now()
                        }));
                }
            };
        ''')
        response = page.goto(ORIGIN)
        assert response.status == 200
        assert '/src/main.tsx' not in response.text(), 'Development frontend was served'
        for path in ['/health', '/health/db', '/docs', '/docs/oauth2-redirect', '/redoc', '/openapi.json']:
            check = page.request.get(ORIGIN + path)
            assert check.status == 200, (path, check.status)
        schema = page.request.get(ORIGIN + '/openapi.json').json()
        assert '/api/v1/jobs/search' in schema['paths']
        assert page.request.get(ORIGIN + '/api/does-not-exist').status == 404
        page.get_by_role('button', name='Search Jobs').wait_for()
        with page.expect_response(lambda r: r.url == ORIGIN + '/api/v1/jobs/search' and r.request.method == 'POST') as started:
            page.get_by_role('button', name='Search Jobs').click()
        assert started.value.status == 202
        run_id = started.value.json()['search_id']
        deadline = time.monotonic() + 960
        incremental = unbuffered = False
        while time.monotonic() < deadline:
            data = page.request.get(ORIGIN + '/api/v1/jobs').json()
            assert data['run']['search_id'] == run_id
            if data['run']['status'] in ('running', 'pending'):
                observed = page.evaluate('window.__sse')
                received = [e for e in observed if e['type'] == 'job_saved' and run_id in e['url']]
                if received:
                    unbuffered = True  # Delivery before terminal state proves proxy streaming.
                    rendered = page.locator('article.job').count()
                    if rendered and data['run']['saved']:
                        incremental = True
            if data['run']['status'] in ('completed', 'failed'):
                break
            page.wait_for_timeout(1000)
        else:
            raise TimeoutError('Discovery did not finish in 16 minutes')
        page.wait_for_timeout(4000)
        assert data['run']['status'] == 'completed', data['run']
        assert incremental and unbuffered, 'No incremental SSE/rendering before completion'
        # Replay the committed stream through Nginx to identify this run's saved jobs.
        replay = page.request.get(ORIGIN + f'/api/v1/jobs/search/{run_id}/events')
        assert replay.status == 200 and 'text/event-stream' in replay.headers['content-type']
        saved_ids = set()
        for block in replay.text().strip().split('\n\n'):
            fields = dict(line.split(': ', 1) for line in block.splitlines() if ': ' in line)
            if fields.get('event') == 'job_saved':
                saved_ids.add(json.loads(fields['data'])['job_id'])
        current_jobs = [j for j in data['jobs'] if j['id'] in saved_ids]
        assert current_jobs and len(current_jobs) == data['run']['saved']
        now = datetime.fromisoformat(data['run']['window_end'])
        for job in current_jobs:
            assert fresh(datetime.fromisoformat(job['posted_date']).date(),
                         datetime.fromisoformat(job['posted_at']) if job['posted_at'] else None, now)
            assert job['description'] and job['title']
            assert page.get_by_role('heading', name=job['title'], exact=True).count()
            detail = page.request.get(ORIGIN + '/api/v1/jobs/' + job['id'])
            assert detail.status == 200 and detail.json()['job_url'] == job['job_url']
        ids = {j['id'] for j in data['jobs']}
        sse = page.evaluate('window.__sse')
        page.reload()
        page.get_by_role('heading', name=data['jobs'][0]['title'], exact=True).first.wait_for()
        after = page.request.get(ORIGIN + '/api/v1/jobs').json()
        assert ids == {j['id'] for j in after['jobs']}
        assert page.locator('article.job').count() == len(ids)
        page.locator('summary').first.click()
        assert page.locator('details').first.get_attribute('open') is not None
        assert not errors, errors
        assert all(url.startswith(ORIGIN + '/') or url == ORIGIN + '/' for url in requests), requests
        page.evaluate('scrollTo(0, 0)')
        page.screenshot(path='/tmp/scraplink-docker-dashboard.png')
        result = {'origin': ORIGIN, 'run': data['run'],
                  'counts': dict(Counter(j['source'] for j in current_jobs)),
                  'incremental_render': incremental, 'sse_before_completion': unbuffered,
                  'sse_job_saved': sum(e['type'] == 'job_saved' and run_id in e['url'] for e in sse),
                  'sse_replayed_jobs': len(saved_ids), 'refresh_persisted': len(ids),
                  'console_errors': errors, 'same_origin_requests': True, 'jobs': current_jobs}
        Path('/tmp/scraplink-docker-acceptance.json').write_text(json.dumps(result, indent=2))
        print(json.dumps({k: v for k, v in result.items() if k != 'jobs'}, indent=2))
        browser.close()


if __name__ == '__main__':
    main()
