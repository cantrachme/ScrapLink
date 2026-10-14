# ScrapLink

Open the dashboard, click **Search Jobs**, and watch genuine recent jobs save
automatically. No forms, manual saving, accounts, filters, or visible browsers.

## Start locally

Requires Docker with Compose. The existing `.env` supplies PostgreSQL credentials
and optional source settings; keep its credentials and the existing database
volume. For a fresh checkout only, copy `.env.example` to `.env` and set the
PostgreSQL password once.

```sh
docker compose build
docker compose up
```

Open **[http://localhost:8000](http://localhost:8000)**. Nginx serves the production
React build on `/` and proxies `/api/*`, `/health*`, `/docs`, `/docs/*`, `/redoc`,
and `/openapi.json` to FastAPI. API and SSE URLs are relative to this same origin.
There is no Vite server at runtime. **Only Nginx publishes a host port: 8000 on
loopback.** PostgreSQL, FastAPI and the worker have no host port mappings.

Compose starts PostgreSQL, applies migrations when starting the API, waits for
API/database and worker readiness, then starts Nginx. The worker has outbound
internet access for public job collection. Database/API traffic stays on a private
Docker network. SSE buffering, caching and gzip are disabled at Nginx.

Ctrl+C stops the foreground stack; `docker compose up` starts it again. The
existing volume `scraplink_scraplink_postgres_data` is explicitly retained. Do not
use `docker compose down -v` unless you intend to delete data. A separate volume
retains Remotive's six-hour cache. Old host/port/DATABASE_URL values in `.env` are
overridden inside Compose so the API and worker always connect to `db:5432`.

## Sources and publication evidence

| Source | Configured employer / retrieval | Freshness evidence |
| --- | --- | --- |
| Ashby | [Ashby](https://jobs.ashbyhq.com/ashby): public metadata + Scrapling extraction of posting HTML/JSON-LD | `publishedAt` (last publication); an older original HTML `datePosted` excludes reposts |
| Greenhouse | [Anthropic](https://job-boards.greenhouse.io/anthropic): public metadata + Scrapling title, location and full description from HTML | `first_published`, never `updated_at` |
| Lever | [Palantir](https://jobs.lever.co/palantir): Scrapling board links and detail HTML; API `createdAt` only orders the scan | HTML JobPosting `datePosted`; creation time never qualifies a job |
| Remotive | [Public jobs API](https://github.com/remotive-io/remote-jobs-api); Scrapling parses description HTML | `publication_date`; timezone is not supplied |
| USAJOBS | Official search API, enabled only with `USAJOBS_EMAIL` and `USAJOBS_API_KEY` | `PublicationStartDate` |

Board tokens are configurable in `.env`, with at most three per employer
platform. LinkedIn and Wellfound have no collection routes or worker execution.
Their reusable offline extraction parsers remain for existing fixtures.

The rolling window is `[run start − 7 days, run start]`. Verified timezone-aware
timestamps are compared in UTC; future, missing and invalid dates are excluded.
Date-only or unspecified-timezone records retain the source text and no invented
`posted_at`. They qualify only when the entire possible calendar day across
UTC−12 through UTC+14 fits inside the window. This deliberately excludes uncertain
boundary days. Original URLs and source IDs are retained; repeat runs upsert the
same jobs. The dashboard retains historical saves, even after their original
seven-day discovery window passes. Missing optional values display as unknown.

## Architecture and bounds

React → Nginx → FastAPI → PostgreSQL queue → existing Python worker → Scrapling →
PostgreSQL jobs/events → SSE → React. Each job and its event commit together.
The database serializes duplicate starts; worker ownership locks prevent duplicate
execution and expose liveness. Nginx is the single public entry point; the
application frameworks are unchanged.

Each source stops at 20 unique qualifying jobs, 1,000 metadata rows, 120 inspected
details, or 180 seconds. Scanning continues past 20 nonqualifying listings. Requests
are sequential, at least one second apart, with 20-second maximum timeouts and no
retries, challenge solving, session import or proxy rotation. Employer HTML requests
respect robots.txt; redirects and blocked responses stop that source visibly.
Failures preserve previous saves and do not prevent other sources from running.
Remotive uses its explicitly permitted redistribution API with a six-hour disk
cache (`/cache/remotive.json` in its named Docker volume), source attribution and original links; its feed is
24 hours delayed. No Remotive webpage challenge is bypassed.

## Verification

```sh
docker compose exec api python -m pytest -q
npm --prefix frontend run test
npm --prefix frontend run build
npm --prefix frontend run lint
git diff --check
# Optional browser acceptance from the existing local Python environment:
# .venv/bin/playwright install chromium
.venv/bin/python scripts/live_acceptance.py
```

Tests use an automatically created isolated PostgreSQL database (the configured
user needs CREATEDB). Fixtures never enter the live queue. The live script clicks
Search Jobs in headless Chromium, checks incremental React rendering and actual
SSE, verifies freshness and full descriptions, reloads, and compares saved IDs.
All browser requests go through `http://localhost:8000`; SSE must arrive before
the run completes. Evidence is written to `/tmp/scraplink-docker-acceptance.json`
and `/tmp/scraplink-docker-dashboard.png`. No host database connection is needed.
See [single-port verification](docs/docker-verification.md),
[earlier extraction results](docs/verification.md), and the [SSE contract](docs/search-events.md).

## Limitations

Coverage is limited to configured boards and scan budgets, not the whole market.
Employer HTML can change. A timeout or access restriction is reported per source;
zero jobs is a legitimate result. Dates certify publication, not that an employer
will still accept an application. USAJOBS needs credentials and is not live-tested
without them. Nginx returns an explicit 503 if FastAPI is unreachable; inspect
`docker compose logs api worker nginx db` for the underlying cause.
