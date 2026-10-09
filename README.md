# ScrapLink MVP — Step 50

React submits searches to FastAPI. A separate Python worker claims PostgreSQL
queue records, opens one Scrapling Chrome session per search, parses listing and
detail pages, filters dates, and persists results. React follows durable SSE
progress and retrieves saved jobs with stable PostgreSQL UUIDs.

```text
React/Vite ──POST search──> FastAPI ──> PostgreSQL pending task + queued event
                                    ↑                   ↓ SKIP LOCKED claim
React <──SSE replay/poll── FastAPI    │       independent JobQueueWorker
React ──GET results/details──────────┘                   ↓
                                      BrowserCollector (one Chrome session)
                                                        ↓
                                      JobExtractionPipeline / source adapters
                                                        ↓
                                      PostgreSQL results + terminal event
```

There are three application processes: API, worker, and React/Vite. PostgreSQL 17
runs in Docker. No browser runs in an API request, and no Redis or Celery is needed.

## Install and initialize

Use Python 3.12, Docker Compose, installed Google Chrome, and a Node version
supported by `frontend/package.json` (for example Node 24.15+ in the 24.x line).
From the repository root:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
# Only for a new checkout; preserve an existing .env:
test -f .env || cp .env.example .env
```

Set `POSTGRES_PASSWORD` in `.env` to your local database password. The default
host port is **5433**. `DATABASE_URL`, when nonempty, overrides the separate
PostgreSQL settings. Never put these credentials in frontend files.

```sh
docker compose up -d
# Wait until docker compose ps reports healthy.
alembic upgrade head
alembic current
alembic check
cd frontend
npm ci
```

Existing installations already at `f81ef2e38717` need no new migration. Step 50
uses existing task timestamps plus PostgreSQL advisory locks for recovery.
Chrome is used through the installed Scrapling/Playwright packages; a separate
Chromium download is unnecessary when Google Chrome is already installed.

## Run locally in four terminals

Run backend commands from the repository root so `.env` is found.

**Terminal 1 — database**

```sh
docker compose up -d
```

**Terminal 2 — API**

```sh
source .venv/bin/activate
uvicorn backend.app.main:app --reload --port 8000
```

**Terminal 3 — worker and local fixture server**

```sh
source .venv/bin/activate
python -m backend.app.workers.run_worker --mode fixture
```

**Terminal 4 — React**

```sh
cd frontend
npm run dev
```

Open [Job Search](http://localhost:5173/search). Choose LinkedIn or Wellfound,
enter **Python Developer**, location **United States**, posting date **Any time**
(`date_posted="any"`), and maximum results **20**. Submit, follow pending → running
→ completed, then open any saved job. Refresh both the search and details page:
they retrieve the same records. Save the search URL; there is no search-history
index yet. For a clearly observable queued state, submit before starting the worker.

Expected demonstration: **4 unique discovered URLs, 3 saved jobs, 1 intentional
detail failure** across two populated listing pages and a final empty page.
An old job is included with Any time; other windows can exclude static timestamps.
A duplicate link on page one and a repeated link on page two are fetched only once.
Descriptions contain multiple sections and an explicit end marker. Compensation,
company, location, employment type, and posting dates are stored.

### Fixture mode is demonstration data only

This mode requires `APP_ENV=development`. The worker starts a loopback HTTP
server at `http://127.0.0.1:8765` automatically, serving `tests/fixtures/e2e/`.
There is no fifth terminal or Docker service. `[DEMO]` titles, a demonstration
company name, and description notices identify synthetic data even after restart.
These are **not genuine LinkedIn or Wellfound jobs**, and canonical source URLs
are parsing identifiers, not real listings to visit or apply to.

The existing source router and pagination builders generate canonical URLs.
An explicit fixture resolver maps only catalog listing/detail URLs to localhost;
source-specific discovery and detail parsing still validate canonical domains.
Unknown catalog URLs fail closed. Fixture searches support Python Developer in
United States, New York, or an empty location; other requests fail rather than
returning unrelated demonstration jobs. Date and result limits still apply.

A real Scrapling DynamicSession navigates the local pages. Context routes allow
only the exact fixture origin, including subresources and redirects. Scripts,
service workers, and WebSockets are disabled; Chrome background networking and
external DNS resolution are disabled for this session. No fixture navigation
or source-link following contacts a platform. The resolver is installed only by
explicit `--mode fixture`; live mode never installs it. Run only one mode against
a given development queue at a time: task records do not have mode routing.
Use a separate database for live data if you need both environments concurrently.

## Worker commands

```sh
python -m backend.app.workers.run_worker --help
python -m backend.app.workers.run_worker --mode fixture --once
python -m backend.app.workers.run_worker --mode fixture --poll-interval 2 --max-pages 10
python -m backend.app.workers.run_worker --mode fixture --headless
python -m backend.app.workers.run_worker --mode fixture --fixture-port 8766
```

`--once` recovers stale tasks, processes at most one pending task, and exits. With
an empty queue it logs that no work exists and opens no Chrome session. Continuous
mode waits two seconds when idle or when PostgreSQL is unavailable; there is no
busy loop. Chrome is visible by default (`BROWSER_HEADLESS=false`), with
`--headless` / `--no-headless` overriding that setting. Browser actions use
`BROWSER_TIMEOUT_MS` (30 seconds by default), with one attempt per navigation.
A page timeout or individual detail failure is recorded; collection may continue
for other details. If no qualifying job is saved and detail failures occurred,
the search fails and persists its detail failures. Valid empty/date-filtered
searches without extraction failures complete with zero jobs.

### Shutdown and stale-task recovery

Ctrl+C or SIGTERM stops new claims and wakes an idle wait immediately. During
collection it stops at the next browser boundary (an in-flight fetch can take its
configured timeout), closes Chrome, and marks the search failed with an operator
shutdown reason and one terminal event. Shutdown does not retry collection.

Each claimed task holds a PostgreSQL **session advisory lock** on a dedicated
AUTOCOMMIT connection, acquired before the running claim commits. This connection
holds no open database transaction or row lock during browser work. Its physical
connection is closed on exit; PostgreSQL also releases it when the process dies.
The lock is the active-execution indication, so a slow browser is not mistaken
for an abandoned worker. One additional connection per active worker is required;
use direct PostgreSQL connections, not a transaction-pooling proxy.

On each poll (and before `--once`), recovery examines up to 100 running records
whose `updated_at` is older than **300 seconds**. Progress refreshes that timestamp.
Recovery locks rows with `FOR UPDATE SKIP LOCKED` and must also acquire the matching
transaction advisory lock. An active worker's session lock prevents recovery,
regardless of task age. Missing ownership plus the stale timeout fails the task
with an abandonment explanation and a terminal event in one transaction. Retained
progress remains replayable. Concurrent recovery produces no duplicate terminal
events, and late collectors cannot publish progress or finish a failed task.

```sh
# Recover abandoned tasks without opening Chrome or starting the fixture server:
python -m backend.app.workers.run_worker --mode fixture --recover-only
# Optional timeout override; keep the normal five-minute grace unless diagnosing:
python -m backend.app.workers.run_worker --mode fixture --recover-only --stale-timeout 300
```

Unexpected process death does not automatically repeat a search. If database
failure prevents writing failure status, a later healthy worker recovers it.
Until PostgreSQL detects a dead connection and releases its lock, recovery waits;
a genuinely hung process retaining ownership must be stopped by its operator.
Previously deployed workers without ownership locks must be stopped before this
worker's recovery is enabled. Submit a new search explicitly if a retry is wanted.

Intermediate events are an audit of progress, not proof that final jobs were
committed. A crash or fatal listing/browser error before final persistence can
leave progress with no saved jobs. This is reported as failure, never completion.
Final results, associations, extraction failures, status and terminal event commit
atomically. Database commit failures cannot expose a premature completed event.

## API, SSE, and persistence

```sh
curl -sS -X POST http://localhost:8000/api/v1/jobs/search \
  -H 'Content-Type: application/json' \
  -d '{"source":"linkedin","keyword":"Python Developer","location":"United States","date_posted":"any","max_results":20}'
```

Use the returned search UUID:

```sh
curl -N http://localhost:8000/api/v1/jobs/search/SEARCH_UUID/events
curl -N -H 'Last-Event-ID: 5' http://localhost:8000/api/v1/jobs/search/SEARCH_UUID/events
curl http://localhost:8000/api/v1/jobs/search/SEARCH_UUID
curl http://localhost:8000/api/v1/jobs/search/SEARCH_UUID/results
curl http://localhost:8000/api/v1/jobs/JOB_UUID
```

The event sequence is queued, started, page discoveries and job outcomes, then
completed or failed. Events have increasing per-search sequence numbers. React
uses cumulative totals and deduplicates sequence IDs; native EventSource resumes
with Last-Event-ID after disconnects. Terminal streams close. Reopened completed
searches fetch persisted results directly; the full event log is still available
through the endpoint. SSE payloads are allow-listed and contain no HTML, cookies,
credentials, or raw exceptions. See [SSE contract](docs/search-events.md).

Repeated URLs do not produce duplicate jobs or associations. Upserts preserve
UUIDs, missing optional data, complete stored descriptions, and known compensation
fields when a partial salary arrives. Searches reference the latest shared job
record, not an immutable snapshot. PostgreSQL persists across API/worker restarts.

## Permitted live collection — separate validation

Live collection is disabled unless the operator explicitly configures sources
for which collection is authorized. Set only the sources you have permission to
collect from in the backend environment, for example:

```sh
AUTHORIZED_LIVE_SOURCES=linkedin python -m backend.app.workers.run_worker --mode live
```

A comma-separated `linkedin,wellfound` permits both. A queued source outside that
list fails with a configuration error. This declaration is not a login mechanism
or proof of platform permission. This MVP uses a fresh browser session and has no
authenticated session import. If a source requires credentials, a login, or access
approval unavailable to that session, stop and report the blocker. HTTP errors,
recognized login/challenge pages and unrecognized empty listing pages fail;
there is no CAPTCHA solver, authentication bypass, proxy rotation, or evasion.

Live validation was **not performed for Step 50**: no authorized access was
configured. Fixture success validates integration and parsers against controlled
HTML; it does not establish that current live markup, filters, pagination, dates,
full descriptions or company/location metadata work. Once permission and access
are available, separately check each of these with a small `--max-pages 1` search,
compare with the source page, and retain failures as evidence. Wellfound supports
only the existing explicit public role/location mappings; arbitrary keywords are
unsupported. Empty-page recognition is conservative and may need adjustment from
authorized live evidence if source markup changes.

## Quality gates

With local PostgreSQL running and migrations applied:

```sh
source .venv/bin/activate
python -m pytest -q
alembic current
alembic check
git diff --check
cd frontend
npm run build
npm run lint
npm run test
```

Normal tests replace browser transport only; they exercise real PostgreSQL,
FastAPI routes, collectors, source adapters and SSE without platform traffic.
Each new integration test uses unique records and cleans them up. Run tests in a
dedicated local test database with no concurrent development workers.

Opt-in real Chrome tests use the local HTTP fixture server:

```sh
SCRAPLINK_BROWSER_TESTS=1 python -m pytest -q tests/test_end_to_end.py -m browser
```

They require installed Google Chrome and permission to connect to loopback. They
run Chrome headlessly to avoid disturbing development; the normal worker defaults
to visible Chrome. They are skipped in the normal suite.

## Stop services and troubleshoot

Stop API, worker and Vite with Ctrl+C, then `docker compose stop`. The database
volume is retained. `docker compose down` also retains it; **do not use `down -v`**
unless you intentionally want to delete PostgreSQL data.

- **Search stays queued:** start the worker with the same `.env`/database as the
  API. The dashboard health indicator checks the API, not worker readiness.
- **Chrome cannot launch:** install Google Chrome, check OS launch permissions,
  use `--headless` in an environment without a display, and inspect worker logs.
  A failed launch produces failed status. Do not use challenge bypass tools.
- **Database unavailable:** check `docker compose ps`, port 5433, `.env`, and
  `GET /health/db`. An existing Docker volume retains its original password even
  after `.env` changes; restore the correct configuration rather than deleting data.
  Continuous workers wait and retry polling; failed searches are not rerun.
- **Fixture port busy:** use `--fixture-port 8766` or `--fixture-port 0` and read
  the logged origin. The fixture server belongs to the worker and closes on exit.
- **Zero fixture jobs:** choose Any time, not a relative date window, and use
  Python Developer in United States. Static fixture dates intentionally stay fixed.
- **SSE reconnecting:** check the API and Vite proxy, reopen the saved search URL,
  or inspect event replay with curl. Never treat extraction progress as final data.
- **Stuck running after a crash:** allow the five-minute grace, start a worker or
  run `--recover-only`; ensure the old process has exited and released its lock.
