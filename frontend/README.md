# ScrapLink frontend — Step 48

React, TypeScript, Vite, and React Router workspace for creating persisted job
searches and following real FastAPI progress. No mock jobs, counts, or worker
activity are displayed. Search history, the full results table, and job details
remain for later steps.

## Local development

Use Node 24.15.0+ in the 24.x line (or the compatible versions declared in
`package.json`), npm, Python 3.12 with the existing backend dependencies, and the
existing PostgreSQL database/migrations. Keep credentials in the backend `.env`,
never in frontend configuration.

From the repository root, start the API using the existing environment:

```sh
source .venv/bin/activate
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

In another terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173`. Vite uses a strict port and proxies relative `/api`
and `/health` paths to `http://127.0.0.1:8000`. The proxy streams SSE without
rewrites or buffering; no WebSocket proxy, CORS change, or frontend environment
variable is required. No additional dependencies were added in Step 48.

The dashboard health indicator still checks only `/health` with an eight-second
timeout. It does not check database or worker readiness.

## Search creation and API integration

| Frontend route | Behavior |
| --- | --- |
| `/` | Dashboard, backend health, links to Job Search |
| `/search` | Controlled search form and source restrictions |
| `/searches/:searchId` | Persisted task, live progress, results summary |
| `/jobs/:jobId` | Existing Step 49 job-details placeholder |
| `*` | Not-found page |

The form posts JSON to `POST /api/v1/jobs/search`. FastAPI returns HTTP 202 with
`search_id`, `status`, and `message`; the current creation status is `pending`.
Successful submission navigates to `/searches/{search_id}` without a document
reload. Opening or refreshing that page only retrieves the existing search.

Inputs and validation:

- Source: LinkedIn (default) or Wellfound.
- Keyword: required, nonblank, at most 200 characters; trimmed on submission.
- Location: United States by default, at most 200 characters; trimmed. Empty
  location means all locations.
- Posting window: `any`, `24h` (default), `7d`, or `30d`.
- Maximum results: integer 1–500, default **20** in this UI (backend default 50).
- Wellfound permits only Software Engineer, Python Developer, Full Stack
  Developer, and Data Engineer, with United States, New York, or empty location.
  These case-insensitive mappings mirror `backend/app/sources/wellfound/search.py`.
  Suggestions and inline errors prevent unsupported submissions; switching
  source preserves the user's inputs.
- Wellfound dates are filtered after extraction. A date window can exclude jobs
  without verifiable dates. Date exclusions are neither extractions nor failures.

`src/lib/api.ts` centralizes URLs, typed creation/retrieval, and runtime checks
for consumed response fields. It displays FastAPI string/list validation
messages, HTTP failures, invalid JSON/schema responses, and network failures.
Requests have a 15-second timeout and abort on page departure. Inputs remain
intact after failure. A synchronous submission guard and disabled controls
prevent concurrent requests. Creation is never automatically retried: after a
network failure or timeout, the backend may already have accepted the task.
The API has no creation idempotency key or search-history endpoint in this UI.

## Search progress and SSE

The page validates canonical UUID syntax before calling:

- `GET /api/v1/jobs/search/{searchId}` for persisted status/request/timestamps.
- `GET /api/v1/jobs/search/{searchId}/events` for active search progress.
- `GET /api/v1/jobs/search/{searchId}/results` for a terminal results summary.

`useSearchEvents` uses native `EventSource` and named listeners:

| Event | UI behavior |
| --- | --- |
| `search_queued` | Queued activity; does not regress an already-running task |
| `search_started` | Running status |
| `page_discovered` | Actual page number and cumulative unique discoveries |
| `job_extracted` | Cumulative qualifying extractions; title and company activity |
| `job_failed` | Cumulative failures and public error summary |
| `search_completed` | Final counters, completed status, close connection |
| `search_failed` | Actual public error, failed status, close connection |

Payloads and sequence IDs are runtime-validated against the backend event
contract. Invalid events are ignored with a visible notice. Heartbeat comments
are handled by the browser and never become activities. See
[`docs/search-events.md`](../docs/search-events.md) for backend semantics.

Native EventSource owns automatic reconnection and `Last-Event-ID`; the hook
never creates a competing retry timer or manually supplies that header. Active
page loads replay from the beginning. Per-connection sequence deduplication,
cumulative totals, and sequence-ordered activity prevent counter inflation.
The timeline renders only the newest 100 events, oldest first, without losing
counters or deduplication of earlier IDs. Public event payloads are expandable
for debugging. SSE payloads do **not** include timestamps, so none are invented.
Persisted creation/update timestamps are displayed separately.

Connectivity is separate from execution status: an open stream cannot turn a
pending task into a running task. A disconnect displays reconnecting and triggers
one task reconciliation (at most one in flight), allowing historical tasks that
end without terminal events to close correctly. There is no HTTP polling while
SSE is healthy. Terminal events close the stream immediately; listeners and
requests are cleaned up on departure/search changes. On completion/failure the
page refreshes persisted metadata and the result summary, with manual summary
reload after an error. A failed stream that cannot reconnect can be reloaded.

A task already completed or failed when opened uses persisted results **without
opening EventSource**. The result response has final counts but no page count or
activity history, so those remain explicitly unavailable on terminal-page loads.
For failed searches opened after termination, intermediate progress counts are
also unavailable: extractions may never have been committed;
the terminal summary describes only persisted records. Full historical timeline
browsing for finished searches is not implemented in this step.

Results remain a summary on the same search page. There are no fabricated job
rows, unsupported cancel/pause/resume actions, or claims that an extraction event
alone confirms database persistence. Step 49 owns the table and detailed job
presentation; the backend currently has no standalone job-details API.

## Worker startup limitation and Step 50 integration

The API creates a PostgreSQL pending task and queued event. It does not start
Chrome or schedule an in-process collector. `JobQueueWorker` implements
`run_once`/`run_forever`, and `BrowserCollector` implements progress callbacks,
but the repository has no executable worker startup entry point wiring them
together. Therefore a reachable API alone can leave searches correctly queued.

Step 50 needs an explicit executable startup path that constructs
`BrowserCollector` with `build_source_search_url`, injects it into
`JobQueueWorker`, and runs the worker with the configured backend environment,
PostgreSQL, and installed browser runtime. It also needs startup/shutdown and
operational documentation. This step does not add that entry point, bypass access
challenges, launch a worker, or make live LinkedIn/Wellfound requests. Existing
worker crashes can leave tasks running; recovery/leases remain backend work.

## Validation

From `frontend/`:

```sh
npm run build
npm run lint
npm run test
```

From the repository root:

```sh
source .venv/bin/activate
python -m pytest -q
git diff --check
```

Vitest uses React Testing Library, mocked fetch, and a deterministic EventSource
mock. Frontend tests require no FastAPI, PostgreSQL, browser collector, or source
network requests. Backend tests require the existing local PostgreSQL and browser
fixture infrastructure. The previous foundation/navigation/health checks remain;
the obsolete assertion that the search page has no inputs now checks the real
form. New suites cover creation, validation, errors/timeouts, duplicate clicks,
retrieval, reload, every event, replay/order/deduplication, malformed payloads,
reconnection, terminal closure, listener cleanup, and capped activity.

## Production

Build with `npm run build` and serve `dist/` behind an HTTPS reverse proxy.
Route `/api` and `/health` to FastAPI before the SPA fallback; serve `index.html`
for other client routes so direct links and browser refresh work. Keep SSE
unbuffered and uncached, forward `Last-Event-ID` and query strings, and configure
idle timeouts for the backend's 15-second heartbeats. Preserve `text/event-stream`,
`Cache-Control`, and `X-Accel-Buffering`. Vite's development proxy is not included
in `dist/`. `npm run preview` is only a local preview server.
