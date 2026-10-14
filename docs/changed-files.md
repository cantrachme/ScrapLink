# Changed files

Relative to committed baseline `a4d60a7`. Existing uncommitted work was adapted,
not reset. No commits or pushes were made. Database models, migrations, persisted
data and reusable offline extraction parsers were preserved. Obsolete browser
execution, forms, routes and their superseded tests/docs were removed after live
extraction succeeded. `react-router` was the only removed direct dependency;
Python packages required by Scrapling or retained utilities remain.

## Added (8)

- `backend/app/sources/discovery.py`
- `backend/app/workers/discovery.py`
- `docs/changed-files.md`
- `docs/verification.md`
- `frontend/src/tests/dashboard.test.tsx`
- `scripts/live_acceptance.py`
- `scripts/start_live.py`
- `tests/test_discovery.py`

## Modified (25)

- `.env.example`
- `.gitignore`
- `README.md`
- `backend/app/api/routes/jobs.py`
- `backend/app/config.py`
- `backend/app/main.py`
- `backend/app/repositories/job_repository.py`
- `backend/app/repositories/search_repository.py`
- `backend/app/schemas/job.py`
- `backend/app/schemas/search_event.py`
- `backend/app/services/search_event_stream.py`
- `backend/app/sources/structured_job.py`
- `backend/app/workers/queue_worker.py`
- `backend/app/workers/run_worker.py`
- `docs/search-events.md`
- `frontend/package-lock.json`
- `frontend/package.json`
- `frontend/src/app/App.tsx`
- `frontend/src/pages/DashboardPage.tsx`
- `frontend/src/styles/globals.css`
- `frontend/vite.config.ts`
- `tests/fixtures/e2e/README.md`
- `tests/test_job_details_api.py`
- `tests/test_search_events.py`
- `tests/test_sse.py`

## Deleted (69)

- `backend/app/services/active_job_details.py`
- `backend/app/services/job_executor.py`
- `backend/app/services/task_manager.py`
- `backend/app/sources/linkedin/search.py`
- `backend/app/sources/pagination.py`
- `backend/app/sources/search_router.py`
- `backend/app/sources/wellfound/search.py`
- `backend/app/workers/active_browser.py`
- `backend/app/workers/active_jobs.py`
- `backend/app/workers/browser_collector.py`
- `backend/app/workers/fixture_site.py`
- `backend/app/workers/live_browser.py`
- `docs/BRD.md`
- `docs/PRD.md`
- `docs/TRD.md`
- `docs/step50-report.md`
- `frontend/README.md`
- `frontend/src/app/router.tsx`
- `frontend/src/components/jobs/ActiveJobsButton.tsx`
- `frontend/src/components/jobs/AssistedJobForm.tsx`
- `frontend/src/components/jobs/ExternalJobLink.tsx`
- `frontend/src/components/jobs/JobResults.tsx`
- `frontend/src/components/layout/AppLayout.tsx`
- `frontend/src/components/layout/Header.tsx`
- `frontend/src/components/layout/Sidebar.tsx`
- `frontend/src/components/ui/Icon.tsx`
- `frontend/src/components/ui/PageHeader.tsx`
- `frontend/src/components/ui/StatusIndicator.tsx`
- `frontend/src/hooks/useSearchEvents.ts`
- `frontend/src/lib/active-options.ts`
- `frontend/src/lib/api.ts`
- `frontend/src/lib/job-contract.ts`
- `frontend/src/lib/job-format.ts`
- `frontend/src/lib/search-contract.ts`
- `frontend/src/lib/search-events.ts`
- `frontend/src/pages/ActiveJobsPage.tsx`
- `frontend/src/pages/JobDetailsPage.tsx`
- `frontend/src/pages/NotFoundPage.tsx`
- `frontend/src/pages/SearchDetailsPage.tsx`
- `frontend/src/pages/SearchPage.tsx`
- `frontend/src/tests/active-jobs.test.tsx`
- `frontend/src/tests/api.test.ts`
- `frontend/src/tests/app.test.tsx`
- `frontend/src/tests/assisted-job.test.tsx`
- `frontend/src/tests/job-api.test.ts`
- `frontend/src/tests/job-details.test.tsx`
- `frontend/src/tests/job-fixtures.ts`
- `frontend/src/tests/job-results.test.tsx`
- `frontend/src/tests/search-events.test.tsx`
- `frontend/src/tests/search-fixtures.ts`
- `frontend/src/tests/search-form.test.tsx`
- `frontend/src/tests/search-progress.test.tsx`
- `frontend/src/types/event.ts`
- `frontend/src/types/job.ts`
- `frontend/src/types/search.ts`
- `tests/test_active_jobs.py`
- `tests/test_browser.py`
- `tests/test_browser_collector.py`
- `tests/test_browser_pagination.py`
- `tests/test_dynamic.py`
- `tests/test_end_to_end.py`
- `tests/test_job_executor.py`
- `tests/test_job_search.py`
- `tests/test_linkedin_search.py`
- `tests/test_live_browser.py`
- `tests/test_pagination.py`
- `tests/test_queue_worker.py`
- `tests/test_wellfound_search.py`
- `tests/test_worker_startup.py`

