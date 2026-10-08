# ScrapLink frontend — Step 47

React, TypeScript, and Vite foundation for the existing FastAPI application.
Includes navigation, responsive pages, typed API contracts, and a real backend
connectivity check. Search submission, EventSource subscriptions, search history,
results, and job details remain for Steps 48–49. No mocked job data is shown.

## Requirements and installation

- Node.js **24.15.0+ in the 24.x line** (the validation environment).
  The installed tooling also supports Node 22.22.2+ in 22.x or Node 26+; see
  `engines` in `package.json`. Node 20 does not meet jsdom's requirements.
- npm (validated with 11.12.1).
- Python 3.12 and the existing backend dependencies for FastAPI.
- The existing PostgreSQL setup for backend database operations/tests.

From the repository root:

```sh
cd frontend
npm ci
```

Version `package.json` and `package-lock.json`. `node_modules/`, `dist/`, local
environment files, and coverage output are ignored.

## Local development

Start FastAPI in a terminal at the repository root, using the existing backend
environment and `.env` configuration (see the root `.env.example`):

```sh
source .venv/bin/activate
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

If needed, first create the Python environment with Python 3.12 and install the
root `requirements.txt`. Keep database settings and credentials in the backend
environment only. This step needs no running worker or live scraping requests.

Start the frontend in another terminal:

```sh
cd frontend
npm run dev
```

Open `http://localhost:5173`. The port is strict: Vite reports a conflict instead
of silently moving to another port. React fast refresh stays enabled. On small
screens the header menu reveals navigation; on desktop the sidebar can collapse.

The browser calls relative paths, so Vite proxies `/api` and `/health` (including
`/health/db`) to `http://127.0.0.1:8000`, preserving the complete request path.
The HTTP proxy also streams SSE; SSE does not need a WebSocket proxy. No backend
CORS changes or frontend environment variables are needed locally.

The dashboard calls only `/health`, initially and when “Check connection” is
pressed. It shows loading, connected, or unavailable, with an eight-second
timeout. Leaving the dashboard aborts the request. This checks API connectivity,
not database/worker readiness. The UI remains usable with FastAPI stopped.

## Routes and contracts

| Route | Current behavior |
| --- | --- |
| `/` | Dashboard, live API connectivity, workflow introduction |
| `/search` | LinkedIn/Wellfound overview and planned search controls; no form |
| `/searches/:searchId` | Search details placeholder; no fetch or ID validation |
| `/jobs/:jobId` | Job details placeholder; no fetch or ID validation |
| `*` | Not found with navigation back to the dashboard |

Routes are centralized in `src/app/router.tsx` using declarative APIs from the
installed `react-router` package. Detail destinations are reserved until real
result data can supply identifiers; there are no invented example links.

`src/lib/api.ts` centralizes existing endpoint paths and provides typed JSON
fetching with HTTP, network, and malformed-JSON errors. Generic types describe
responses at compile time; they are not runtime schema validation.

Types in `src/types/` mirror `backend/app/schemas/job.py`,
`backend/app/services/task_manager.py`, and `backend/app/schemas/search_event.py`.
Optional request fields reflect backend defaults. Response fields with defaults
are present in FastAPI's JSON; nullable values are represented with `null`.
Dates/datetimes are strings. `JobSource` includes `realpython_demo` for returned
records, while creation accepts only LinkedIn or Wellfound. SSE payloads use the
seven actual event names; see [`docs/search-events.md`](../docs/search-events.md).
Event IDs are sequence strings; database timestamps are not sent in SSE frames.

## Validation

From `frontend/`:

```sh
npm run build
npm run lint
npm run test
npm run test:watch
```

The build checks strict TypeScript before generating `dist/`. ESLint covers
TypeScript and React hooks/fast refresh. Vitest uses jsdom, React Testing Library,
and jest-dom with mocked `fetch`; frontend tests require no live services.

From the repository root:

```sh
source .venv/bin/activate
python -m pytest -q
git diff --check
```

## Production

```sh
cd frontend
npm run build
npm run preview
```

`preview` serves built files locally, normally on port 4173; it is not a production
server. Vite can reuse the development proxy for preview. Proxy configuration is
not included in `dist/`.

Deploy `dist/` behind an HTTPS web server/reverse proxy. Route `/api`, `/health`,
and `/health/db` to FastAPI **before** the SPA fallback; serve `index.html` for
other client routes so deep links and refreshes work. Keep SSE unbuffered and
uncached, forward `Last-Event-ID` and query strings, and configure idle timeouts
for the backend's 15-second heartbeats. Preserve its `text/event-stream`,
`Cache-Control`, and `X-Accel-Buffering` headers.

This foundation uses a same-origin reverse proxy in production. If a separate API
origin is needed later, configure it in the API utility and future EventSource
URLs together and explicitly configure the backend's allowed origin. Any `VITE_*`
variable is public build output and must never contain credentials or secrets.

No authentication, billing, database connections, search submission, or SSE
subscription is implemented in React in this step. The backend exposes jobs
through search results, not a standalone `/jobs/:jobId` API; Step 49 must account
for that when connecting the reserved frontend route.
