"""Opt-in REAL internet acceptance. Requires scripts/start_live.py running.
Clicks the real React button in headless Chromium, verifies SSE and persistence.
Writes evidence to /tmp/scraplink-acceptance.json and a dashboard screenshot.
"""
import json
import sys
import time
from pathlib import Path
from collections import Counter

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.sources.discovery import fresh
from datetime import datetime


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1280, 'height': 900})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('http://127.0.0.1:5173/')
        page.get_by_role('button', name='Search Jobs').wait_for()
        page.evaluate('window.__sse = []')
        page.add_init_script('window.__sse = []')
        # Observe actual native SSE messages without replacing fetch or EventSource.
        page.evaluate('''() => {
            const Native = window.EventSource;
            window.EventSource = class extends Native {
                constructor(url) { super(url); for (const name of ['job_saved', 'search_completed', 'source_status'])
                    this.addEventListener(name, e => window.__sse.push({type:name, data:JSON.parse(e.data)})); }
            };
        }''')
        page.get_by_role('button', name='Search Jobs').click()
        deadline = time.monotonic() + 960
        incremental = False
        while time.monotonic() < deadline:
            data = page.request.get('http://127.0.0.1:5173/api/v1/jobs').json()
            if data['run'] and data['run']['status'] in ('running', 'pending'):
                if data['jobs'] and page.locator('article.job').count(): incremental = True
            if data['run'] and data['run']['status'] in ('completed', 'failed'): break
            page.wait_for_timeout(1000)
        else: raise TimeoutError('Discovery did not finish in 16 minutes')
        page.wait_for_timeout(4000)
        assert data['run']['status'] == 'completed', data['run']
        assert data['jobs'], 'No genuine qualifying jobs returned; do not claim acceptance'
        assert incremental, 'Jobs were not rendered incrementally'
        sse = page.evaluate('window.__sse')
        assert any(e['type'] == 'job_saved' for e in sse), 'No actual job_saved SSE received'
        ids = {j['id'] for j in data['jobs']}
        now = datetime.fromisoformat(data['run']['window_end'])
        from backend.app.database import SessionLocal
        from backend.app.models.search import SearchTaskJob
        from sqlalchemy import select
        from uuid import UUID
        with SessionLocal() as db:
            run_ids = set(str(value) for value in db.scalars(select(SearchTaskJob.job_id).where(
                SearchTaskJob.search_id == UUID(data['run']['search_id']))))
        current_jobs = [job for job in data['jobs'] if job['id'] in run_ids]
        assert len(current_jobs) == data['run']['saved']
        for job in current_jobs:
            assert fresh(datetime.fromisoformat(job['posted_date']).date(),
                         datetime.fromisoformat(job['posted_at']) if job['posted_at'] else None, now)
            assert job['description'] and job['title']
            assert page.get_by_role('heading', name=job['title'], exact=True).count()
        page.reload()
        page.get_by_role('heading', name=data['jobs'][0]['title'], exact=True).first.wait_for()
        after = page.request.get('http://127.0.0.1:5173/api/v1/jobs').json()
        assert ids == {j['id'] for j in after['jobs']}
        assert page.locator('article.job').count() == len(ids)
        page.locator('summary').first.click()
        assert page.locator('details').first.get_attribute('open') is not None
        assert not errors, errors
        page.screenshot(path='/tmp/scraplink-dashboard.png', full_page=False)
        result = {'run': data['run'], 'counts': dict(Counter(j['source'] for j in current_jobs)),
                  'incremental_render': incremental, 'sse_job_saved': sum(e['type']=='job_saved' for e in sse),
                  'refresh_persisted': len(ids), 'console_errors': errors, 'jobs': current_jobs}
        Path('/tmp/scraplink-acceptance.json').write_text(json.dumps(result, indent=2))
        print(json.dumps({k:v for k,v in result.items() if k != 'jobs'}, indent=2))
        browser.close()


if __name__ == '__main__': main()
