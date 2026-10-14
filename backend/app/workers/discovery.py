"""Incremental transactions shared by the queue worker and real-source collectors."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from backend.app.config import settings
from backend.app.database import SessionLocal
from backend.app.models.job import Job
from backend.app.models.search import SearchTaskJob
from backend.app.repositories.job_repository import JobRepository
from backend.app.repositories.search_repository import utc_now
from backend.app.schemas.job import JobSource
from backend.app.sources.discovery import LIMIT, fresh

SOURCES = ('ashby', 'greenhouse', 'lever', 'remotive', 'usajobs')


def run_discovery(worker, search_id, request):
    now = datetime.fromisoformat(request['window_end'])
    failed_sources = 0
    for source in SOURCES:
        worker.check_shutdown()
        saved_ids = set()

        def report(status, stats, error=None):
            worker.check_shutdown()
            with SessionLocal.begin() as db:
                task = worker.repository._get_locked(db, search_id)
                if task.status != 'running':
                    raise RuntimeError('Search execution ownership lost')
                task.updated_at = utc_now()
                worker.events.publish(db, search_id, 'source_status', {
                    'source': source, 'status': status, **stats, 'error': error,
                })

        def save(job):
            worker.check_shutdown()
            if job.source != JobSource(source) or not fresh(job.posted_date, job.posted_at, now):
                raise ValueError('Collector returned wrong source or unverified publication date')
            if len(saved_ids) >= LIMIT:
                raise ValueError('Per-source result limit exceeded')
            with SessionLocal.begin() as db:
                task = worker.repository._get_locked(db, search_id)
                if task.status != 'running':
                    raise RuntimeError('Search execution ownership lost')
                # One discovery run globally; task lock also fences all writes.
                existing = db.scalar(select(Job).where(Job.source == source,
                    Job.source_job_id == job.source_job_id).order_by(Job.first_seen_at).limit(1)) if job.source_job_id else None
                if existing:
                    job = job.model_copy(update={'job_url': existing.job_url})
                saved = JobRepository.upsert(db, job)
                inserted = db.execute(insert(SearchTaskJob).values(search_id=search_id, job_id=saved.id)
                    .on_conflict_do_nothing().returning(SearchTaskJob.job_id)).scalar()
                if inserted:
                    task.total_extracted += 1
                    task.updated_at = utc_now()
                    # Job, association, count and event commit together. SSE reads committed rows.
                    worker.events.publish(db, search_id, 'job_saved', {
                        'source': source, 'job_id': str(saved.id), 'total_extracted': task.total_extracted,
                    })
                saved_ids.add(saved.id)

        empty = {'scanned': 0, 'saved': 0, 'undated': 0}
        if source == 'usajobs' and not (settings.USAJOBS_EMAIL and settings.USAJOBS_API_KEY):
            report('disabled', empty, 'USAJOBS requires USAJOBS_EMAIL and USAJOBS_API_KEY')
            continue
        try:
            worker.collector.collect(source, now, save, report)
        except Exception as exc:
            worker.check_shutdown()
            failed_sources += 1
            stats = worker.collector.stats()
            report('failed', stats, f'{type(exc).__name__}: {exc}')
        with SessionLocal.begin() as db:
            task = worker.repository._get_locked(db, search_id)
            task.total_discovered += worker.collector.stats()['scanned']
            task.total_failed = failed_sources
    with SessionLocal.begin() as db:
        task = worker.repository._get_locked(db, search_id)
        task.status = 'completed'
        task.finished_at = task.updated_at = utc_now()
        worker.events.publish(db, search_id, 'search_completed', {
            'search_id': str(search_id), 'status': 'completed',
            'total_discovered': task.total_discovered, 'total_extracted': task.total_extracted,
            'total_failed': task.total_failed,
        })
