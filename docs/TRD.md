# ScrapLink — Technical Requirements Document (TRD)

| Attribute | Value |
|---|---|
| Product | ScrapLink |
| Document | Technical Requirements Document |
| Version | 1.0 — Draft architecture |
| Date | 2026-10-08 |
| State | Proposed implementation; no architecture is implemented yet |
| Related documents | [BRD.md](./BRD.md), [PRD.md](./PRD.md) |

## 1. Technical objective and design constraints

Build a React + FastAPI application that submits job searches, runs Scrapling-powered extraction in a separate Python worker, persists normalized job listings, and streams status using SSE.

**Critical boundary:** LinkedIn is the desired business target but not an approved scraper endpoint. The collection layer must enforce a provider allowlist and authorization status. Test extraction on owned pages, fixtures, or approved sources first. Do not implement CAPTCHA bypass, stealth/evasion against a prohibited target, session hijacking, or unauthorized login automation.

Design objectives:

- Separate HTTP application from long-running browser workloads.
- Make providers interchangeable via a typed adapter interface.
- Guarantee job/run durability independent of live SSE connections.
- Ensure repeatable and bounded task execution.
- Expose unknown/partial states faithfully.
- Support easy local development and container deployment.

## 2. Selected and proposed stack

| Concern | Choice | Status |
|---|---|---|
| Language | Python 3.12 | Installed locally |
| Collection | Scrapling with fetcher/browser extras | Proposed; not yet installed |
| Backend API | FastAPI + Uvicorn | Proposed |
| Frontend | React + TypeScript + Vite | Proposed |
| Database | PostgreSQL | Proposed; changeable with migration |
| ORM / migrations | SQLAlchemy 2.x + Alembic | Proposed |
| Durable job queue | PostgreSQL-backed task table initially | Proposed MVP simplification |
| Worker | Separate Python process sharing backend code | Proposed |
| Realtime | SSE over FastAPI `StreamingResponse` | Proposed |
| Package / tooling | pip + requirements files, Ruff, pytest | Proposed |
| Deployment | Docker Compose local; cloud approach later | Proposed |

**Why no Redis/Celery initially?** A Postgres-backed queue with one bounded worker avoids maintaining another service during a small pilot. If throughput, retry, or scheduling requirements grow, migrate to Redis + RQ/Dramatiq/Celery or another broker. Do not run browser work as an in-process FastAPI `BackgroundTasks` substitute for a durable queue.

## 3. Architecture

```mermaid
flowchart LR
    U[React UI] -->|REST| API[FastAPI]
    U <-->|SSE| API
    API --> DB[(PostgreSQL)]
    W[Python worker] --> DB
    W --> G[Approved provider adapter]
    G --> S[Scrapling fetcher/browser]
    S --> P[Permitted source]
    W --> N[Normalize + validate]
    N --> DB
```

### Responsibilities

- **React:** form validation, run progress, job table/detail, reconnection handling.
- **FastAPI:** input validation, create/read/cancel runs, listing queries, SSE with authorization checks.
- **Postgres:** canonical run status, job records, source settings, progress events, durable task claims.
- **Worker:** claim queued tasks, fetch data, parse, deduplicate, commit updates, handle retry/cancel.
- **Provider adapters:** site-specific search construction, pagination, extraction, policy constraints, optional status checking.

## 4. Proposed repository structure

```text
ScrapLink/
├── docs/
│   ├── BRD.md
│   ├── PRD.md
│   └── TRD.md
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── routes_searches.py
│   │   │   ├── routes_jobs.py
│   │   │   └── routes_events.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   └── source_policy.py
│   │   ├── db/
│   │   │   ├── base.py
│   │   │   ├── models.py
│   │   │   └── session.py
│   │   ├── schemas/
│   │   │   ├── search.py
│   │   │   └── job.py
│   │   ├── services/
│   │   │   ├── search_service.py
│   │   │   ├── job_service.py
│   │   │   └── event_service.py
│   │   ├── collectors/
│   │   │   ├── base.py
│   │   │   ├── registry.py
│   │   │   └── fixture_provider.py
│   │   └── worker/
│   │       ├── main.py
│   │       └── runner.py
│   ├── alembic/
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── pages/
│   │   └── types/
│   ├── package.json
│   └── vite.config.ts
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

This is a target layout, not an existing directory tree.

## 5. Domain model and database design

Prefer UUID primary keys, timezone-aware timestamps, foreign keys, unique constraints, and indexes aligned to queries.

### 5.1 `sources`

| Column | Type | Meaning |
|---|---|---|
| id | text PK | Stable adapter code, e.g. `approved_careers_a` |
| name | text | Display name |
| enabled | boolean | Whether tasks may use source |
| authorization_status | enum/text | `approved`, `pending`, `disabled` |
| permitted_patterns | JSONB | Allowed URL patterns, reviewed by operator |
| policy_notes | text | Review scope and limits |
| last_reviewed_at | timestamptz nullable | Access review timestamp |

Only `enabled=true` AND `authorization_status='approved'` may be scheduled. Approval must be controlled server-side and never set by an untrusted search request.

### 5.2 `search_runs`

| Column | Type | Meaning |
|---|---|---|
| id | UUID PK | Run identifier |
| query | JSONB | Immutable validated search snapshot |
| status | text | Lifecycle status |
| counters | JSONB | Typed counters |
| error_summary | text nullable | Safe user-facing summary |
| idempotency_key | text nullable UNIQUE | Avoid duplicate submissions |
| created_at | timestamptz | Created UTC |
| started_at | timestamptz nullable | Started UTC |
| finished_at | timestamptz nullable | Ended UTC |
| heartbeat_at | timestamptz nullable | Worker liveness |
| cancel_requested_at | timestamptz nullable | Cancellation intent |
| attempt | integer | Task execution attempt |
| next_attempt_at | timestamptz nullable | Retry schedule |
| lease_owner | text nullable | Claimed worker ID |
| lease_expires_at | timestamptz nullable | Claim expiry |

**Lifecycle:** `queued → running → completed | completed_with_errors | failed | cancelled`. An internal `cancelling` state may be used while draining. Retries should preserve run identity; terminal updates must be idempotent.

### 5.3 `jobs`

| Column | Type | Meaning |
|---|---|---|
| id | UUID PK | Internal job ID |
| source_id | text FK | Source adapter |
| source_job_id | text nullable | Stable ID if source provides it |
| canonical_url | text | Normalized original URL |
| title | text | Required, nonblank |
| company | text nullable | Company |
| location_raw | text nullable | Source value |
| location_normalized | text nullable | Conservative normalized form |
| workplace_type | text nullable | remote/hybrid/onsite/unknown |
| employment_type | text nullable | full-time/etc. |
| description | text nullable | Only if permitted to retain |
| posted_at | timestamptz nullable | Parsed timestamp |
| posted_at_precision | text | exact/date_only/relative_estimate/unknown |
| posted_raw | text nullable | Original presentation if allowed |
| activity_status | text | active/unknown/closed |
| activity_evidence | text nullable | Reason supporting verified status |
| first_seen_at | timestamptz | Initial discovery |
| last_seen_at | timestamptz | Latest successful discovery |
| last_verified_at | timestamptz nullable | Latest meaningful activity check |
| created_at / updated_at | timestamptz | Audit timestamps |

**Uniqueness:** unique `(source_id, source_job_id)` when job ID is non-null, and unique `(source_id, canonical_url)` for URL fallback. Use database constraints and `INSERT ... ON CONFLICT` (or ORM equivalent). Do not merge cross-provider rows based solely on title/company.

### 5.4 `run_jobs`

Join table (`run_id`, `job_id`, `observed_at`) allowing the same job to appear in many runs while preserving per-run result filtering. Unique `(run_id, job_id)`.

### 5.5 `run_events`

| Column | Type | Meaning |
|---|---|---|
| id | bigint generated PK | Monotonically increasing event ID |
| run_id | UUID FK | Run reference |
| type | text | status/progress/job_found/warning/error |
| payload | JSONB | Non-secret event body |
| created_at | timestamptz | Event time |

Index `(run_id, id)` for ordered event replay. Retain bounded event history. Before pruning, confirm SSE reconnect window and use snapshot fallback.

### 5.6 `run_errors` (optional but recommended)

`id`, `run_id`, `source_id`, `stage`, `error_code`, `safe_message`, `occurred_at`. Never store secrets or entire authenticated HTML dumps in general logs.

## 6. REST API contract (proposed `/api/v1`)

### 6.1 Create run

`POST /api/v1/search-runs`

```json
{
  "keywords": "Software Engineer",
  "location": "United States",
  "posted_within": "24h",
  "sources": ["approved_careers_a"]
}
```

Use header `Idempotency-Key: <client-generated-uuid>` for retries. Server validates allowed sources and returns **202 Accepted**:

```json
{
  "id": "1b4daef4-8ee5-4a90-947b-896c89bdfd98",
  "status": "queued",
  "created_at": "2026-10-08T00:00:00Z"
}
```

IDs and dates above are illustrative API examples, not actual run records.

### 6.2 Get run

`GET /api/v1/search-runs/{run_id}` → run status, query snapshot, timestamps, counters, source warnings, and completion reason.

### 6.3 Cancel run

`POST /api/v1/search-runs/{run_id}/cancel` → **202** on accepted cancellation request; idempotent when already cancelled. Return a terminal status unchanged when finished.

### 6.4 List jobs

`GET /api/v1/jobs?run_id=...&status=unknown&source_id=...&sort=first_seen_desc&limit=25&offset=0`

Return:

```json
{
  "items": [],
  "total": 0,
  "limit": 25,
  "offset": 0
}
```

Whitelist sortable fields, cap `limit` (e.g. at 100), parameterize filters, and return a stable secondary sort by ID. Prefer cursor pagination if data volume grows.

### 6.5 Job detail

`GET /api/v1/jobs/{job_id}` → complete permitted job fields and provenance.

### 6.6 Allowed sources

`GET /api/v1/sources` → approved, enabled sources and supported filter capabilities. Do not expose internal permission artifacts, credentials, or sensitive source configuration.

### 6.7 Health

`GET /health/live` (process alive), `GET /health/ready` (database dependency reachable).

### 6.8 Error shape

```json
{
  "error": {
    "code": "SOURCE_NOT_ALLOWED",
    "message": "This source is not enabled for automated collection."
  }
}
```

Use appropriate HTTP codes: 400/422 validation, 403 unauthorized source, 404 missing record, 409 conflicting active operation, 429 limits, 500 unexpected server error.

## 7. SSE design

`GET /api/v1/search-runs/{run_id}/events`

Headers: `Content-Type: text/event-stream`, `Cache-Control: no-cache`; reverse proxy buffering disabled for stream routes.

Example:

```text
id: 1205
event: progress
data: {"run_id":"1b4daef4-8ee5-4a90-947b-896c89bdfd98","status":"running","pages_visited":4,"new_jobs":12}

id: 1206
event: completed
data: {"run_id":"1b4daef4-8ee5-4a90-947b-896c89bdfd98","status":"completed"}

```

- Persist events before or atomically with the corresponding durable state changes.
- Use `Last-Event-ID` to replay retained events for **the requested run only**.
- On missing/pruned ID, client must GET a fresh run snapshot.
- Send comment keepalives during idle periods; ensure they do not falsely indicate progress.
- If no authorization model exists, bind local-only mode to localhost; add authentication before public deployment.
- Native `EventSource` cannot send arbitrary auth headers; use same-site secure cookies when auth is added or a deliberate fetch-stream alternative. Do not place long-lived API tokens in URLs.
- The SSE connection is a **read channel**, not where collection executes. Database is source of truth.

## 8. Collection pipeline and adapters

### 8.1 Contract

Define a provider interface conceptually:

```python
from typing import AsyncIterator, Protocol

class JobSourceAdapter(Protocol):
    source_id: str

    async def search(self, query: "SearchQuery") -> AsyncIterator["RawJob"]:
        ...

    async def check_activity(self, job: "Job") -> "ActivityEvidence":
        ...
```

`check_activity` can return `unknown` or be unimplemented for a source; do not falsely infer activity. Use Pydantic models for typed records, avoid leaking Scrapling objects into service and API layers.

### 8.2 Responsibilities

1. **Registry:** expose only approved enabled adapters.
2. **Query translation:** convert generic filters to provider-supported requests; record unsupported filters.
3. **Fetching:** use Scrapling `Fetcher` for static permitted pages; `DynamicFetcher` for JavaScript-driven permitted pages.
4. **Parsing:** site-specific extraction from DOM; configurable selectors with test fixtures.
5. **Pagination:** follow bounded, validated next-page links within approved scope.
6. **Normalize:** trim text, canonicalize URLs, parse dates conservatively, validate required fields.
7. **Persist:** transaction-safe upserts, record run/job association and counters.
8. **Progress:** append events and update durable run status.
9. **Finish:** completed/completed-with-errors/failed/cancelled based on actual results and errors.

### 8.3 Adaptive selectors

Scrapling supports CSS/XPath-based selection and adaptive relocation of previously matched elements. Treat adaptive matches as **heuristic**, not guaranteed correctness. Validate parsed fields and catch sudden changes in field completeness. Pin and test the Scrapling version before production use.

Official docs: https://scrapling.readthedocs.io/en/latest/

### 8.4 Browser sessions

- Start with fresh worker-managed contexts on permitted sites.
- Never use or extract a user's unrelated existing Chrome cookies/profile by default.
- If authenticated integration becomes authorized, use an explicit, securely stored connection mechanism, separate per tenant and source, with revocation and access controls.
- Set page/navigation timeouts and always close contexts in `finally` blocks.
- Use bounded concurrency and request budgets; do not override source access restrictions.

## 9. Worker scheduling and fault tolerance

### 9.1 Proposed Postgres queue

A single worker polls queued runs and claims them using transactional row locking, e.g. `SELECT ... FOR UPDATE SKIP LOCKED`, to prevent two workers from claiming the same available task. Record `lease_owner`, `lease_expires_at`, and `heartbeat_at`. Renew lease while working; recover expired claims on worker restart.

### 9.2 Safety and limits

- Max one concurrent browser-run initially; make configurable.
- Cap pages/results per run and execution time.
- Use provider-specific concurrency and delay limits.
- Bounded retry for transient network failures with backoff; permanent permission/4xx failures should not loop.
- The same run can be retried; database upserts must be idempotent.
- Source-level failures should not hide prior successful results.
- Circuit-break or disable a provider when policy status changes or repeated failures require review.

### 9.3 Cancellation

Mark `cancel_requested_at`. Worker checks between pages/items and before scheduling another page. Release browser resources and persist final status in `finally`. Never delete already saved results on cancel.

## 10. Normalization and identity rules

- Strip fragments and known tracking parameters from URLs only when safe for the source's URL semantics; keep the original URL separately if required.
- Source ID is scoped to provider, not globally unique.
- `posted_at` is a datetime only if supported by parseable evidence; otherwise null.
- Relative posting time estimates are anchored to fetch time and tagged `relative_estimate`.
- Avoid reverse engineering a timezone where none is shown.
- Preserve activity status `unknown` when inaccessible, missing, or contradictory.
- Require explicit open/closed evidence for `active` / `closed`.
- For job deduplication, prefer source ID + native job ID, then source ID + canonical URL; do not silently merge cross-source matches.

## 11. Frontend implementation

### React modules

- `SearchForm`: controlled inputs, client validation, submission.
- `RunStatus`: lifecycle, counts, warnings, cancellation.
- `useRunEvents(runId)`: EventSource lifecycle/reconnect and snapshot refresh.
- `JobsTable`: server queries, pagination, sorting, filtering.
- `JobDetails`: provenance, timestamps, activity evidence.
- `apiClient`: typed endpoints, timeout/error parsing.

### Data lifecycle

1. On submit, POST run.
2. Store run ID in route/query state to allow reloads.
3. GET initial run snapshot.
4. Subscribe to SSE, refresh result page on relevant events with debouncing.
5. After disconnect, reconnect and re-fetch canonical snapshot.
6. Show explicit terminal result even if SSE event arrives late or is missed.

Prefer a typed response layer (TypeScript interfaces or generated OpenAPI client), TanStack Query or equivalent for HTTP state, and an accessible component library or straightforward CSS. Avoid introducing extra state infrastructure without a need.

## 12. Security and compliance

- Treat URLs, HTML, and source-provided text as untrusted. Do not interpolate raw source HTML into React; render escaped text or sanitized approved content.
- Prevent SSRF: only adapters may construct permitted destination URLs; validate scheme, host and redirects; block private/loopback/link-local/metadata endpoints.
- Keep source approvals in server configuration/DB with an administrative review process.
- Secrets in `.env` locally and a managed secret store in production; `.env` is Git-ignored.
- Use least privilege for database and worker accounts.
- Protect API and SSE endpoints with authentication before exposing a production instance.
- Configure CORS for explicit frontend origins, not unrestricted credentials origins.
- Implement API request limits and global worker/browser budgets.
- Restrict retention of raw HTML, descriptions, events and logs according to license/policy.
- Do not expose credentials, session cookies or raw HTML in logs or SSE.
- Do not use stealth features to circumvent provider security restrictions.

**LinkedIn-specific decision:** Its documented policies prohibit unauthorized browser bots/scraping. A LinkedIn provider must remain disabled until an approved integration path is documented and validated. See the source and product constraints in BRD/PRD.

## 13. Environment and deployment

### Local development proposal

- Python virtual environment: `.venv` with Python 3.12.
- Frontend Node.js LTS compatible with the selected Vite version.
- PostgreSQL in Docker Compose (or local Postgres).
- Separate terminals/processes for API, worker and Vite frontend.
- `scrapling[fetchers]` and browser dependencies installed as documented by Scrapling.

### Environment variables (examples, not real secrets)

```dotenv
APP_ENV=development
DATABASE_URL=postgresql+psycopg://scraplink:change_me@localhost:5432/scraplink
FRONTEND_ORIGIN=http://localhost:5173
API_HOST=127.0.0.1
API_PORT=8000
WORKER_CONCURRENCY=1
MAX_PAGES_PER_RUN=20
MAX_RESULTS_PER_RUN=200
EVENT_RETENTION_DAYS=7
```

Use `.env.example` with placeholders but **never commit a real `.env`**. Production secrets and deployment choices need a separate configuration review.

### Docker services (target)

- `db`: PostgreSQL with persistent volume and health check.
- `api`: FastAPI/Uvicorn HTTP process; runs DB migrations as a controlled release step.
- `worker`: separate Python worker image/process; browser dependencies bundled.
- `frontend`: Vite for local development or compiled static assets behind a web server for production.

Do not run browser jobs inside the React client or API request threads.

## 14. Observability and operations

Track run ID, provider, worker ID, stage, duration, requests, pages, jobs parsed, validation failures, upserts, retry counts, and end state. Structured logs should redact secrets/PII. Suggested metrics:

- `runs_started_total`, `runs_completed_total`, `runs_failed_total`
- `job_records_valid_total`, `job_records_rejected_total`, `job_records_deduplicated_total`
- `fetch_duration_seconds`, `pages_fetched_total`, `source_errors_total`
- `worker_lease_expirations_total`, `sse_connections_active`

Alert on worker stalls, unbounded queue age, high extraction-rejection rate, repeated permission errors, and zero-result anomalies against historically nonempty sources. Avoid treating zero results alone as conclusive failure.

## 15. Testing plan

| Level | Tests |
|---|---|
| Unit | Normalization, date precision, allowed URL checks, status transitions, dedup keys |
| Parser fixture | Stable saved HTML fixture from permitted source; missing/reordered elements |
| Contract | API request validation and typed responses |
| Database | Unique constraints, idempotent upsert, run/result joins, migrations |
| Worker | Claim/lease/retry/cancel and crash recovery |
| SSE | Ordering, reconnect via Last-Event-ID, snapshot fallback |
| Frontend | Form validation, empty/error/partial views, filters and pagination |
| End-to-end | Approved test source → queue → browser/parser → DB → SSE → UI |
| Security | SSRF redirects/host allowlists, XSS escaping, secret redaction |

No live scraping test should run against an unapproved provider. CI should rely on local deterministic fixtures and mocked browser/network behavior.

## 16. Implementation plan and checkpoints

### Milestone 0 — specification and permissions

- Confirm initial authorized source.
- Approve minimum job schema, validation semantics, and filters.
- Confirm single-user/local MVP vs public hosted access.

**Exit:** approved test source and reviewed requirements.

### Milestone 1 — project skeleton

- `backend/` FastAPI health endpoint and settings.
- `frontend/` Vite React TypeScript page.
- `db` Compose service and Alembic migration baseline.
- Tests, lint and README.

**Exit:** all processes start locally and health checks pass.

### Milestone 2 — job extraction proof of concept

- Install Scrapling fetchers/browser dependencies.
- Build fixture/approved-source adapter.
- Test one static and one JS-rendered permitted page where practical.
- Return normalized records through internal typed models.

**Exit:** a verified source fixture parses fields deterministically.

### Milestone 3 — durable runs and data

- Create search, job, source, run-job, event models/migrations.
- Add queued run claim/lease, status transitions, cancellation and retry.
- Implement upsert, dedupe, search listing endpoints.

**Exit:** a run persists results after API restart and worker retry.

### Milestone 4 — user interface and SSE

- Search form, run view, results table and detail panel.
- SSE stream and client snapshot recovery.
- Error/partial states and pagination.

**Exit:** a user can search, watch progress, inspect results and recover from refresh.

### Milestone 5 — hardening and pilot

- Full automated tests, bounded execution, logging and source permission review.
- Docker documentation and simple deployment.
- Baseline extraction accuracy, dedup rate, runtime and browser resource usage.

**Exit:** pilot criteria from BRD and PRD pass for approved sources.

## 17. Technical decisions to confirm before coding

1. **First permitted provider:** company career pages, licensed feed, or controlled fixtures.
2. **Authorization:** internal localhost-only initially or login from day one.
3. **Queue:** Postgres-only as proposed, unless existing infrastructure warrants Redis.
4. **Database:** PostgreSQL versus an alternative already operated by the team.
5. **Job description retention:** full text, excerpt or link only, dependent on license.
6. **Browser mode:** headed for local debugging, headless for permitted deployment.
7. **Frontend UI kit:** choose once design work begins.
8. **Hosting:** local first and production environment later.

## 18. Official technical and policy references

- Scrapling documentation: https://scrapling.readthedocs.io/en/latest/
- Scrapling fetching guide: https://scrapling.readthedocs.io/en/latest/fetching/choosing.html
- Scrapling PyPI installation: https://pypi.org/project/scrapling/
- FastAPI documentation: https://fastapi.tiangolo.com/
- PostgreSQL documentation: https://www.postgresql.org/docs/
- LinkedIn prohibited software: https://www.linkedin.com/help/linkedin/answer/a1341387/prohibition-of-scraping-software
- LinkedIn terms: https://www.linkedin.com/legal/user-agreement
