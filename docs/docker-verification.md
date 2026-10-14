# Single-port Docker deployment — 14 October 2026

## Startup and routes

```sh
docker compose build
docker compose up
```

Public application: **http://localhost:8000**. Nginx serves the production-built
React assets at `/`. It proxies `/api/*`, `/health*`, `/docs`, `/docs/*`, `/redoc`,
and `/openapi.json`, preserving query strings, the public Host, and SSE cursors.
The API receives HTTP/1.1 connections with buffering, caching, and gzip disabled.

Changes: added the backend Dockerfile, multi-stage frontend/Nginx Dockerfile,
`.dockerignore`, and `docker/nginx.conf`; updated Compose, source configuration,
startup error messages, README, and browser acceptance. Removed the host-process
launcher and Vite development-server scripts/configuration. The application UI,
collection policies, database models, and migrations remain unchanged.

## Ports and data

Verified with Docker inspection and host socket checks:

| Service | Host bindings |
| --- | --- |
| Nginx | `127.0.0.1:8000 → 80/tcp` |
| FastAPI | None |
| Worker | None |
| PostgreSQL | None |

Ports **5173 and 5433 are closed**. The old host API, worker and Vite processes
were stopped. Docker's `5432/tcp` image metadata is not a host port binding.
The application network has `internal=true`; only Nginx and the worker also join
the egress network. The worker needs egress to retrieve public jobs.

The existing volume **scraplink_scraplink_postgres_data** is mounted at
`/var/lib/postgresql/data`. PostgreSQL recognized the existing database and skipped
initialization. All **26 existing dashboard job UUIDs** were identical before and
after the move. A pre-migration SQL backup is stored locally at
`/tmp/scraplink-before-docker.sql`. No volume or application data was deleted.

## Checks

- `docker compose build`: passed (Python backend and production React/Nginx images).
- `docker compose up`: started PostgreSQL, migrations/API, worker and Nginx in
  health-gated order; all four services became healthy.
- `nginx -t`: passed.
- Backend tests **inside Docker**, using an isolated temporary database: **152 passed**.
- Frontend tests: **5 passed**. Production build, ESLint and Git whitespace checks passed.
- Existing upstream FastAPI/httpx and lxml deprecation warnings remain.

Live browser and restart evidence follows below.


## Live acceptance through Nginx — passed

Run `ecd19a73-15dc-4fbf-ae17-34daed136faf`, window ending `2026-10-14T11:20:14.094221+00:00` (16:50:14 IST).
The headless browser clicked the real **Search Jobs** button at
`http://localhost:8000`. All observed page/asset/API/SSE requests used that origin;
no development server or host database connection was used.

| Source | Jobs saved this run | Result |
| --- | ---: | --- |
| Ashby / Ashby | 2 | 63 metadata records checked; real posting HTML retrieved |
| Greenhouse / Anthropic | 20 | 20 recent posting HTML pages retrieved; result cap reached |
| Lever / Palantir | 0 | Board HTML retrieved; public metadata API timed out |
| Remotive | 1 | Public feed retrieved; 15 records checked |
| USAJOBS | 0 | Disabled because credentials are absent |

**23 saved-job SSE events reached the browser**, with event delivery observed
while the run was still in progress, proving that Nginx streamed incrementally.
The final SSE replay
also returned 23 saved job IDs. React displayed incremental progress and saved
jobs. Full descriptions, original hrefs, date qualification, and individual job
API responses were verified. After refresh, **all 26 dashboard records** remained,
including the three Lever jobs saved before the Docker migration. Console errors:
zero. The source limitation is visible independently; it does not stop other sources.

`/health`, `/health/db`, `/docs`, `/docs/oauth2-redirect`, `/redoc`, and
`/openapi.json` returned HTTP 200 through Nginx. An unknown API route returned
JSON 404 rather than React HTML. The original HTML contained production assets,
not a Vite `/src/main.tsx` entry. SSE `Last-Event-ID` replay also worked through
the proxy and returned an empty terminal stream at the latest cursor.

A full `docker compose stop` / `docker compose up` cycle retained all 26 original
UUIDs, restored worker readiness, and kept ports 5173 and 5433 closed.

Evidence: `/tmp/scraplink-docker-acceptance.json`,
`/tmp/scraplink-docker-dashboard.png`, `/tmp/scraplink-compose.log`, and
`/tmp/scraplink-before-docker.json`. These are verification outputs, not application
fixtures. No changes were committed or pushed.

The API-outage check passed: stopping FastAPI produced an explicit Nginx JSON
**503** in approximately five seconds, while `/` continued serving the production
frontend with HTTP 200. Starting FastAPI restored API access, all 26 jobs, and
worker readiness. Evidence: `/tmp/scraplink-docker-outage.json`.
