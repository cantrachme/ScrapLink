# ScrapLink MVP

The existing React → FastAPI → PostgreSQL queue → Scrapling/Playwright worker
architecture is retained. No migration is required. Live mode never installs a
fixture resolver, substitutes a keyword, or supplies demonstration jobs.

## Run

Requires the existing `.venv`, frontend dependencies, installed Google Chrome,
and PostgreSQL credentials in `.env`. From the repository root:

```sh
docker compose up -d
.venv/bin/alembic upgrade head
```

Run these in three terminals:

```sh
.venv/bin/uvicorn backend.app.main:app --reload --port 8000
```

```sh
.venv/bin/python -m backend.app.workers.run_worker --mode live
```

```sh
npm --prefix frontend run dev
```

Open [Job Search](http://localhost:5173/search), choose CareerHub, enter any
keyword (for example **Software Developer**), leave location empty or use
**Midrand**, choose **Any time**, and start. Watch mode defaults to visible
Chrome with two seconds between actions, configurable to 1.5–3 seconds in the
form. Chrome clicks the search field, types your exact keyword, submits the
form, scrolls to matching cards, clicks listings, and inspects descriptions.
The browser closes when collection finishes. SSE reports completed actions,
real discoveries and extraction outcomes; CareerHub final results commit atomically.
Active Jobs saves each qualifying listing immediately, as described below.

The API and worker must run on the machine with the visible Chrome display.
Only the worker opens Chrome. A queued search waits until a worker is running.
`--once` processes at most one queued request; `--recover-only` recovers abandoned
searches. Ctrl+C stops at the next browser boundary. Existing advisory-lock
recovery, URL deduplication, result UUIDs, date filtering and SSE replay remain.

## Active Jobs

Click **Active Jobs** in the sidebar or dashboard to enqueue one combined
LinkedIn + Wellfound discovery and open its dashboard. There is no keyword,
job title, or location input or substitution. The existing live worker processes
both sources independently. Chrome is always visible; Watch mode and its
1.5–3 second delay, plus a shared maximum of 1–500 saved jobs, can be configured
on the Active Jobs page for the next run. LinkedIn receives `sortBy=DD` and
`f_TPR=r86400` with no keyword/location parameters. Wellfound opens `/jobs` and
uses an exposed native newest-first select when available; no undocumented
sort parameter or fixed role URL is supplied. Both parsers check detail evidence.

**Access:** automation is disabled by default for both platforms. The worker
opens ordinary Chrome and reports each source's authorization limitation.
Use the source's normal UI yourself, then save permitted details using the
form on the dashboard. Source, title, company, location, workplace type,
published salary, posting date/evidence, complete available description and
original URL are supported. Missing values remain unknown; manual entries
are user supplied and do not establish verified recency or active status.

Only an operator with explicit, current platform authorization covering this
collection may configure `ACTIVE_JOBS_AUTHORIZATIONS` in the worker environment
as a JSON object mapping `linkedin` and/or `wellfound` to the permission record
reference. Login access or public visibility alone is not that authorization.
The default is `{}`. Ordinary Job Search remains assisted for these sources.
No authorization has been supplied or enabled as part of this implementation.
Authorized collection stops at authentication, CAPTCHA, access challenges,
HTTP restrictions or off-source navigation; it does not import sessions,
solve challenges, retry blocked access or substitute demonstration data.
The deployed markup and access policy must still permit the configured workflow.

**Persistence and evidence:** each job and its `job_saved` event commit in the
same short PostgreSQL transaction before browser work resumes. React refreshes
saved records on that SSE event, including while the task is running. Source
errors are stored and displayed independently; completed saves survive failures
and recovery. The first source receives half the available result budget (at
least one), preserving room for the second. Source/job-ID deduplication retains
the first navigable URL even across slug or tracking aliases. Different
platform IDs remain separate source-labeled records. Known posting dates sort
newest first, with unknown dates last; source-relative age text is preserved
without inventing a timestamp. Only conservatively verified ages within 24
hours qualify automatically, and expired/explicitly closed jobs are excluded.
Missing dates are not silently replaced with the discovery date. Inspection
records a verification time while availability remains `unknown`.

`POST /api/v1/jobs/active` accepts `max_results`, `watch_mode`, and
`watch_delay_seconds`. It reuses search status/results/event routes, queue
ownership, parsers and job detail views. `?follow=true` on an Active Jobs SSE
stream keeps it open after discovery to receive later assisted saves. No schema
migration is required. Live mode has no fixture fallback.

Validation uses an isolated PostgreSQL database and test-only browser response
interception. The visible Chrome integration test can be run with:

```sh
SCRAPLINK_BROWSER_TESTS=1 .venv/bin/python -m pytest -q tests/test_active_jobs.py
```

## Source behavior and limitations

- **CareerHub**: public South African job listings. Its [terms](https://careerhub.za-worknow.com/terms)
  prohibit scraping that degrades service; its [crawler rules](https://careerhub.za-worknow.com/robots.txt)
  allow public job pages. Collection uses one results page and at most 20 detail
  visits, with at least 1.5 seconds between actions even with Watch mode off.
  There is no separate location control: ScrapLink explicitly reports and applies
  a case-insensitive location-text filter after inspection. Posting dates are not
  supplied, so date windows exclude these undated jobs; use Any time. Descriptions
  are the text published by CareerHub, which may be a summary. The saved original
  URL is the CareerHub detail page actually inspected; external employer/apply
  pages are not visited. Empty results are valid, never replaced with another role.
- **LinkedIn / Wellfound**: user-assisted only. The worker opens ordinary Chrome
  on the selected site's jobs page, then completes the browser handoff. Enter your
  requested keyword and location yourself. Copy a listing's title and original
  URL into **Save a job from your browser** on the search details page. Location,
  Remote/Hybrid/On-site and description are optional. Saved jobs appear in the
  existing results/detail views. These are user-entered, not automatically verified.
  No login, CAPTCHA solving, browser session import or automated scraping occurs.
- Unsupported sources are rejected by the API. Access gates, HTTP errors and
  unrecognized markup fail visibly. No retry, bypass, proxy rotation or evasion.

Title and URL suffice to save a job. Missing company uses an empty string for
compatibility with the existing non-null PostgreSQL column; partial updates
preserve a previously known company. Existing historical demo records stay
labeled `[DEMO]`; new live searches never create them.

## Tests

Fixtures are confined to isolated tests. The fixture worker requires
`APP_ENV=test`; use a separate test database, never the live queue. Legacy
Wellfound role URL mappings are used only by the fixture/parser tests, not live
search. Normal tests make no automated requests to job platforms.

```sh
.venv/bin/python -m pytest -q
npm --prefix frontend run test
npm --prefix frontend run build
npm --prefix frontend run lint
git diff --check
```

Opt-in local Chrome tests (no platform requests):

```sh
SCRAPLINK_BROWSER_TESTS=1 .venv/bin/python -m pytest -q tests/test_end_to_end.py -m browser
```

See [SSE contract](docs/search-events.md). Browser action events contain only an
allow-listed action identifier, never page HTML, cookies or credentials.

## Verified locally — 9 October 2026

CareerHub was verified end to end through the React form, visible Chrome,
real UI search, listing click, SSE activity, PostgreSQL persistence and the job
details page. **Software Developer / Midrand** saved **Junior Software Developer
at AdaptIT**. An exact **DevOps Engineer** search returned zero results without
substitution. LinkedIn and Wellfound automatic collection was not attempted;
assisted saving was covered by isolated API/UI tests. Jobtrude was unavailable
(Cloudflare Tunnel error) and is not an implemented source.
