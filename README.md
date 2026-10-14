# ScrapLink

Open the dashboard, click **Search Jobs**, and watch genuine recent jobs save
automatically. No forms, manual saving, accounts, filters, or visible browsers.

## Start locally

Requires Python 3.12, Node 22.22.2+ (or a supported newer release), Docker,
and the existing project dependencies. First setup:

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
npm --prefix frontend ci
cp .env.example .env
# Set POSTGRES_PASSWORD in .env (keep existing .env/database credentials if present).
```

Start from the repository root:

```sh
docker compose up -d --wait
.venv/bin/python scripts/start_live.py
```

Open [ScrapLink](http://127.0.0.1:5173/). The launcher checks PostgreSQL, applies
existing migrations, and supervises FastAPI, the queue worker, and Vite in one
terminal. Ctrl+C stops all three. PostgreSQL retains its named volume. No browser
installation is needed for collection. The live acceptance script uses headless
Playwright Chromium; install it once with `.venv/bin/playwright install chromium`.

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

React → FastAPI → PostgreSQL queue → existing Python worker → Scrapling →
PostgreSQL jobs/events → SSE → React. Each job and its event commit together.
The database serializes duplicate starts; worker ownership locks prevent duplicate
execution and expose liveness. No additional services or frameworks were added.

Each source stops at 20 unique qualifying jobs, 1,000 metadata rows, 120 inspected
details, or 180 seconds. Scanning continues past 20 nonqualifying listings. Requests
are sequential, at least one second apart, with 20-second maximum timeouts and no
retries, challenge solving, session import or proxy rotation. Employer HTML requests
respect robots.txt; redirects and blocked responses stop that source visibly.
Failures preserve previous saves and do not prevent other sources from running.
Remotive uses its explicitly permitted redistribution API with a six-hour disk
cache (`.cache/remotive.json`), source attribution and original links; its feed is
24 hours delayed. No Remotive webpage challenge is bypassed.

## Verification

```sh
.venv/bin/python -m pytest -q
npm --prefix frontend run test
npm --prefix frontend run build
npm --prefix frontend run lint
git diff --check
# With the app running; real network calls and real database saves:
.venv/bin/python scripts/live_acceptance.py
```

Tests use an automatically created isolated PostgreSQL database (the configured
user needs CREATEDB). Fixtures never enter the live queue. The live script clicks
Search Jobs in headless Chromium, checks incremental React rendering and actual
SSE, verifies freshness and full descriptions, reloads, and compares saved IDs.
Evidence is written to `/tmp/scraplink-acceptance.json` and a screenshot beside it.
See [verification results](docs/verification.md) and [SSE contract](docs/search-events.md).

## Limitations

Coverage is limited to configured boards and scan budgets, not the whole market.
Employer HTML can change. A timeout or access restriction is reported per source;
zero jobs is a legitimate result. Dates certify publication, not that an employer
will still accept an application. USAJOBS needs credentials and is not live-tested
without them. The Vite proxy is for local development; a deployed build needs a
same-origin `/api` reverse proxy that streams SSE without buffering.
