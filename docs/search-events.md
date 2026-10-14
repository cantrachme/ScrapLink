# Discovery events

All routes below are served through Nginx at **http://localhost:8000**. Nginx
forwards the original path and Last-Event-ID, uses HTTP/1.1 upstream, and disables
response/request buffering, caching, and gzip. Its stream read timeout is one
hour; FastAPI sends heartbeats while idle. FastAPI has no published host port.

`POST /api/v1/jobs/search` takes no search parameters. It returns the current
pending/running discovery or queues one fixed seven-day run. A PostgreSQL
transaction advisory lock serializes starts across API processes. A missing
worker returns a descriptive 503. `GET /api/v1/jobs` returns saved discovery jobs,
the latest run, source progress, and worker availability.

`GET /api/v1/jobs/search/{id}/events` streams durable SSE. `Last-Event-ID` takes
precedence over `?after=`. Both are validated nonnegative 32-bit sequence values.
Events are ordered per run, stored in PostgreSQL, replayed after reconnect, and
read in short transactions. Heartbeats occur after 15 seconds without events.
The stream closes after terminal events; React also reconciles every 3 seconds.

- `search_queued`, `search_started`: run ID and status.
- `source_status`: source, status, scanned/saved/undated counts, optional error.
  States: collecting, completed, limit_reached, failed, disabled. Zero is valid.
- `job_saved`: stored job UUID, source, total saved count. Job upsert, run link,
  count and event commit together before the stream can see the event.
- `search_completed`: counts; individual sources may have failed.
- `search_failed`: interrupted run. Earlier successful saves remain available.

The worker owns a session advisory lock for liveness and one for each claimed
run. Short row locks fence writes. On restart, abandoned runs become failed;
they are never silently re-enqueued. Historical/manual/demo records are preserved
but excluded from the dashboard by discovery-run membership. Automated tests
create and drop a separate PostgreSQL database; there is no fixture worker mode.
