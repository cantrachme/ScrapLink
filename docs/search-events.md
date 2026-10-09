# Durable search progress (Steps 46–50)

`GET /api/v1/jobs/search/{search_id}/events` streams the committed PostgreSQL
event log as UTF-8 `text/event-stream`. The API and worker can run in separate
processes. No in-memory message queue, extra dependency, or browser execution in
the search-creation request is involved.

## Event contract

Every event has a per-search integer sequence, starting at 1, an event type,
a JSON object payload, and a timezone-aware creation timestamp. The SSE `id`
is the sequence; `event` is the event type; `data` is the JSON payload.

| Event | Payload fields | Meaning |
| --- | --- | --- |
| `search_queued` | `search_id`, `status: pending`, `source` | API committed the new search and event together. |
| `search_started` | `search_id`, `status: running`, `source` | Worker committed its claim and event together. |
| `page_discovered` | `page_number`, `new_jobs_discovered`, `total_discovered` | Listing parsed and unique URLs accumulated, before processing its details. Empty or duplicate-only pages emit zero new jobs. |
| `job_extracted` | `job_url`, `title`, `company`, `total_extracted` | Detail parsed and accepted by posting-date filtering. Final job persistence may still fail. |
| `job_failed` | `job_url`, `error`, `total_failed` | An individual detail fetch or extraction failed. |
| `search_completed` | `search_id`, `status: completed`, `total_discovered`, `total_extracted`, `total_failed` | Results, failures, completed status, and this event committed atomically. |
| `search_failed` | `search_id`, `status: failed`, `error` | Failed status and terminal event committed atomically. |

Counters match `PipelineResult`: discovered counts unique source job identities,
extracted counts accepted jobs, and failed counts actual fetch/extraction
failures. Discovered URLs can include details never attempted because the result
limit was reached. Old, future, or undated jobs excluded by strict date validation
are neither extractions nor failures. Rediscovery does not trigger another
detail fetch or extraction event. `job_filtered` is not implemented.

Payloads use strict, allow-listed schemas. Arbitrary browser objects, HTML,
cookies, credentials, request payloads, and exception text are not copied into
events. Job URL query strings and fragments are removed, and embedded URL
credentials are rejected. Title/company must be plain text. Public error
summaries are deliberately fixed: the collector emits `Job detail fetching or
extraction failed`; the worker emits `Search execution failed`. The schema also
accepts `Job description unavailable` and `Browser execution failed`. Existing
failure records and worker logging retain their prior semantics.

## Persistence and collection

`SearchEventRepository.publish(db, search_id, event_type, payload)` locks the
parent search row before reading the maximum sequence, inserts and flushes the
next event, and returns an independent DTO. It never commits. Under the existing
PostgreSQL READ COMMITTED isolation, competing publishers wait for the parent
lock and then see the previous publisher's committed sequence. A rollback
removes the event and permits reuse of its uncommitted number.

The `(search_id, sequence)` composite primary key creates the PostgreSQL B-tree
index used for ordered range scans; an identical secondary index would be
redundant. Deleting the parent search cascades to its events.

`get_after(db, search_id, after_sequence, limit=100)` returns ordered DTOs for
`sequence > after_sequence`. It rejects missing searches, negative cursors,
and limits outside 1–1000. ORM objects never cross into the SSE coroutine.

The worker commits the claim before calling the collector. Each callback writes
and commits one progress event in a short, separate transaction. No database
transaction or row lock spans browser actions. Step 50 holds one dedicated
AUTOCOMMIT connection with a session advisory lock as execution ownership; this
connection remains outside a PostgreSQL transaction during browser work. Callback errors escape the
collector, are logged by the worker, and fail the search; if failed-state/event
persistence also fails, the error propagates to the caller.

`BrowserCollector.collect_with_progress(source, request, progress=None)` accepts
a synchronous `progress(event_type: str, payload: dict) -> None` callback scoped
to that invocation. Its existing `__call__(source, request)` still works. The
worker uses the progress method when available and otherwise calls the legacy
two-argument collector exactly once. Legacy fake collectors receive lifecycle
events but cannot supply intermediate progress. One browser session still covers
all pages and details.

## Streaming and reconnection

```sh
curl -N http://localhost:8000/api/v1/jobs/search/SEARCH_UUID/events
curl -N -H 'Last-Event-ID: 5' http://localhost:8000/api/v1/jobs/search/SEARCH_UUID/events
curl -N 'http://localhost:8000/api/v1/jobs/search/SEARCH_UUID/events?after=5'
```

Example frame (followed by a blank line):

```text
id: 2
event: search_started
data: {"search_id":"...","status":"running","source":"linkedin"}

```

`Last-Event-ID` takes precedence over `after`, including a header value of `0`.
Both supplied values are validated. Cursors must be ASCII decimal integers from
0 through 2147483647; malformed, negative, and out-of-range cursors return 422.
An invalid UUID returns 422; an unknown UUID returns 404 before streaming starts.

Reads run in the existing bounded thread pool and use the shared, bounded
SQLAlchemy connection pool. Each read closes its session before returning.
The stream drains batches of 100 events immediately, then polls once per second
while active. Idle connections receive `: heartbeat` comments every 15 seconds.
Responses set `Cache-Control: no-cache` and `X-Accel-Buffering: no`.

Disconnects stop delivery without removing stored events. Cancellation or a
parent deleted during streaming also ends the stream. Reconnecting resumes
strictly after the chosen sequence, including events committed while disconnected.
Completed and failed searches replay all remaining events and close once drained;
reconnecting at or beyond the last sequence returns an empty stream. Browser
clients should call `EventSource.close()` when receiving a terminal event to
prevent the browser from repeatedly reconnecting after normal server closure.

## Migration and verification

Migration `f81ef2e38717` adds only `search_events`, its primary-key index, and its
cascading foreign key, following `1f28dd80f951`. Existing migrations and tables
are unchanged. Its generated upgrade was reviewed before application.

Tests use local PostgreSQL plus fake browser sessions, never real LinkedIn or
Wellfound requests. Concurrency tests observe PostgreSQL lock waits; SSE tests
use bounded async timeouts so an unterminated stream fails instead of hanging.
Coverage includes rollback, cross-session visibility, cascading deletion,
worker transaction failures, progress semantics, batch replay, cursor validation,
heartbeats, polling, UTF-8 formatting, disconnection, and reconnection.

## Known limitations

- Step 50 recovers abandoned `running` tasks after five minutes without a task
  update and only when no execution advisory lock remains. Recovery records
  failed status and one terminal event atomically. Progress stays replayable;
  jobs not committed before a crash are unavailable. No automatic retry occurs.
  See the [worker recovery policy](../README.md#shutdown-and-stale-task-recovery).
- Polling introduces roughly one second of delivery latency and database reads
  per connected client. This local MVP has no LISTEN/NOTIFY or fan-out broker.
- Events are retained until the parent search is deleted; no retention policy
  or event-log compaction is implemented.
- Existing historical searches are not backfilled. A terminal search with no
  terminal event (including the legacy HTML executor) replays whatever events
  exist and closes based on its persisted terminal status.
- Intermediate extraction events are durable progress, not a guarantee that
  the final results transaction will succeed. Only `search_completed` confirms it.

## Step 50 worker integration

Run `python -m backend.app.workers.run_worker --mode fixture` independently of
FastAPI. This wires BrowserCollector to the existing source router and pipeline.
The local demonstration uses real Chrome with loopback-only fixture navigation.
Use `--mode live` only with explicitly configured authorized sources; fixture
results do not validate real platform behavior.

Progress publication checks the locked task is still running, fencing late
collectors after recovery. Shutdown via SIGINT/SIGTERM cooperatively ends
collection and publishes `search_failed` with an operator reason on the task.
A crash loses the execution lock and is recovered after the configured grace.
All-detail failure persists extraction failures and `search_failed` together.
Successful/partially successful final results still use `search_completed`; a
legitimate empty or fully date-filtered result without extraction errors completes.
Both terminal paths retain the original event schemas and transaction atomicity.

The React hook already handles cumulative counters, replay and terminal closure,
so Step 50 does not change its logic. New end-to-end tests assert the actual worker
event order, per-search sequences, cursor replay and absence of duplicate terminal
events, including concurrent recovery after an abrupt subprocess exit.

### Visible browser actions

`browser_action` carries `{ "action": "typed_keyword" }`, emitted only after
that action succeeds. Allowed actions: `opened_source`, `focused_keyword`,
`typed_keyword`, `submitted_search`, `inspected_results`, `scrolled_listing`,
`opened_listing`, `inspected_description`, `returned_results`. Additional factual
notices are `location_filter_local`, `filtered_job` and `manual_required`.
The last reports a browser handoff, not scraping. Manual saves happen after the
handoff completes and refresh persisted results through the API; they do not
fabricate scraping events or reopen the terminal SSE stream.
