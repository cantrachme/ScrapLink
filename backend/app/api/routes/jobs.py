from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.app.database import SessionLocal, get_db
from backend.app.models.job import Job
from backend.app.models.search import SearchTaskRecord, SearchTaskJob
from backend.app.models.search_event import SearchEvent
from backend.app.repositories.search_event_repository import SearchEventRepository
from backend.app.repositories.search_repository import utc_now
from backend.app.schemas.job import PersistedJobResponse
from backend.app.services.search_event_stream import stream_search_events
from backend.app.workers.execution_lock import lock_key
from backend.app.workers.run_worker import WORKER_ID

router = APIRouter(prefix='/jobs', tags=['Jobs'])
DISCOVERY = SearchTaskRecord.request_payload['mode'].as_string() == 'discovery'
START_LOCK = 53435241504


def worker_available(db):
    # A free lock means no live worker. Transaction-scoped probe cannot leak locks.
    return not db.scalar(text('SELECT pg_try_advisory_xact_lock(:key)'), {'key': lock_key(WORKER_ID)})


def run_summary(db, task):
    if task is None:
        return None
    sources = {}
    for event in db.scalars(select(SearchEvent).where(SearchEvent.search_id == task.search_id,
                            SearchEvent.event_type == 'source_status').order_by(SearchEvent.sequence)):
        sources[event.payload['source']] = event.payload
    return {'search_id': str(task.search_id), 'status': task.status, 'sources': sources,
            'saved': task.total_extracted, 'error': task.error, 'created_at': task.created_at,
            'window_end': task.request_payload['window_end']}


@router.post('/search', status_code=202)
def start_search(db: Session = Depends(get_db)):
    db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': START_LOCK})
    task = db.scalar(select(SearchTaskRecord).where(DISCOVERY,
        SearchTaskRecord.status.in_(['pending', 'running'])).order_by(SearchTaskRecord.created_at.desc()).limit(1))
    if task is None:
        if not worker_available(db):
            raise HTTPException(503, 'Discovery worker is not running. Start the app with docker compose up')
        task = SearchTaskRecord(search_id=uuid4(), source=None, status='pending',
            request_payload={'mode': 'discovery', 'window_end': utc_now().isoformat()})
        db.add(task)
        db.flush()
        SearchEventRepository.publish(db, task.search_id, 'search_queued', {
            'search_id': str(task.search_id), 'status': 'pending', 'source': 'multi'})
    db.commit()
    return run_summary(db, task)


@router.get('')
def dashboard(db: Session = Depends(get_db)):
    task = db.scalar(select(SearchTaskRecord).where(DISCOVERY)
                     .order_by(SearchTaskRecord.created_at.desc()).limit(1))
    # Only records saved by this live workflow; old/manual/demo data stays intact.
    linked = select(SearchTaskJob.job_id).join(SearchTaskRecord).where(DISCOVERY)
    jobs = db.scalars(select(Job).where(Job.id.in_(linked))
                     .order_by(Job.posted_date.desc(), Job.posted_at.desc().nulls_last(), Job.id)).all()
    return {'jobs': [PersistedJobResponse.model_validate(j, from_attributes=True) for j in jobs],
            'run': run_summary(db, task), 'worker_available': worker_available(db)}


def parse_event_cursor(value):
    if value is None:
        return 0
    if not value.isascii() or not value.isdecimal() or len(value) > 10 or int(value) > 2_147_483_647:
        raise HTTPException(422, 'Event cursor must be a nonnegative 32-bit integer')
    return int(value)


@router.get('/search/{search_id}/events')
def events(search_id: UUID, request: Request, after: str | None = Query(None),
           last_event_id: str | None = Header(None, alias='Last-Event-ID')):
    cursor = parse_event_cursor(after)
    header = parse_event_cursor(last_event_id)
    if last_event_id is not None:
        cursor = header
    with SessionLocal() as db:
        if db.scalar(select(SearchTaskRecord.search_id).where(DISCOVERY, SearchTaskRecord.search_id == search_id)) is None:
            raise HTTPException(404, 'Discovery run not found')
    return StreamingResponse(stream_search_events(request, search_id, cursor), media_type='text/event-stream',
                             headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@router.get('/{job_id}', response_model=PersistedJobResponse)
def get_job(job_id: UUID, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, 'Job not found')
    return PersistedJobResponse.model_validate(job, from_attributes=True)
