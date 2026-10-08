import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { PageHeader } from '../components/ui/PageHeader'
import { ApiError, getJobSearch, getSearchResults } from '../lib/api'
import { DATE_LABELS, isSearchId, isTerminal } from '../lib/search-contract'
import { activityMessage } from '../lib/search-events'
import { useSearchEvents } from '../hooks/useSearchEvents'
import { JobResults } from '../components/jobs/JobResults'
import type { JobSearchResultsResponse, SearchTask } from '../types/search'

const statusLabels = { pending: 'Queued', running: 'Running', completed: 'Completed', failed: 'Failed' }
const connectionLabels = { connecting: 'Connecting to live progress…', live: 'Live progress connected',
  reconnecting: 'Reconnecting to live progress…', closed: 'Live connection closed', unavailable: 'Live progress unavailable. Reload this page to reconnect.' }
const time = (value: string) => new Date(value).toLocaleString()

function SearchProgress({ task }: { task: SearchTask }) {
  const progress = useSearchEvents(task)
  const [latest, setLatest] = useState(task)
  const [results, setResults] = useState<JobSearchResultsResponse | null>(null)
  const [resultsError, setResultsError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const terminal = isTerminal(progress.status)

  useEffect(() => {
    if (!terminal) return
    const controller = new AbortController()
    getSearchResults(task.search_id, controller.signal).then((summary) => {
      if (!controller.signal.aborted) { setResults(summary); setResultsError('') }
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setResultsError(cause instanceof Error ? cause.message : 'Unable to load persisted results.')
    })
    return () => controller.abort()
  }, [terminal, task.search_id, attempt])

  useEffect(() => {
    // A reopened terminal task already has persisted metadata. Refresh only
    // when an active task terminates, independently of manual result retries.
    if (!terminal || isTerminal(task.status)) return
    const controller = new AbortController()
    getJobSearch(task.search_id, controller.signal).then((value) => {
      if (!controller.signal.aborted) setLatest(value)
    }).catch(() => { /* Event status remains authoritative if this refresh fails. */ })
    return () => controller.abort()
  }, [terminal, task.search_id, task.status])

  const completed = progress.status === 'completed'
  const discovered = completed && results ? results.total_discovered : progress.discovered
  const extracted = completed && results ? results.total_extracted : progress.extracted
  const failed = completed && results ? results.total_failed : progress.failed
  const hasFinalCounts = !!results || progress.events.some((e) => e.event === 'search_completed')
  const historic = isTerminal(task.status)
  // Failed tasks may have emitted progress without committing any result records.
  const historicalCountsUnavailable = historic && (task.status === 'failed' || !results)
  const metrics = [
    ['Unique jobs discovered', historicalCountsUnavailable ? '—' : historic ? results!.total_discovered : discovered],
    ['Qualifying jobs extracted', historicalCountsUnavailable ? '—' : historic ? results!.total_extracted : extracted],
    ['Failed extractions', historicalCountsUnavailable ? '—' : historic ? results!.total_failed : failed],
    ['Pages processed', progress.pages ?? '—'],
  ]
  return (
    <div className="search-details-stack">
      <section className="card" aria-labelledby="search-status-title">
        <div className="section-heading">
          <h2 id="search-status-title">Search progress</h2>
          <span className={`status task-${progress.status}`} role="status">{statusLabels[progress.status]}</span>
        </div>
        <p className={`connection-note connection-${progress.connection}`} role="status">{connectionLabels[progress.connection]}</p>
        {progress.status === 'pending' && <p className="notice">Waiting for a worker. Your search is safely queued; an active worker must claim it before collection begins. Worker startup integration is planned for Step 50.</p>}
        {progress.status === 'running' && <p className="notice">{progress.events.some((e) => ['page_discovered', 'job_extracted', 'job_failed'].includes(e.event)) ? 'The worker is collecting jobs.' : 'The search is running. Waiting for collection progress.'}</p>}
        {completed && <p className="notice">{hasFinalCounts ? extracted === 0 ? 'Search completed with zero qualifying jobs.' : `Search completed — ${extracted} qualifying jobs extracted.` : resultsError ? 'Search completed. Persisted result counts are currently unavailable.' : 'Search completed. Loading persisted result counts…'} <a className="text-link" href="#search-results">View persisted results summary</a></p>}
        {progress.status === 'failed' && <p className="error-banner" role="alert">Search failed — {latest.error || progress.error || 'The backend did not provide an error message.'}</p>}
        {progress.warning && <p className="notice" role="alert">{progress.warning}</p>}
        <dl className="progress-metrics">{metrics.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
        {(failed > 0 || (results?.total_failed ?? 0) > 0) && <p className="search-note">Some job extractions failed. Qualifying jobs and extraction failures are counted separately.</p>}
        <p className="search-note">Date-filter exclusions are not failures. Extraction progress does not confirm final database persistence. Pages are available only from progress events.</p>
        <dl className="request-summary">
          <div><dt>Search ID</dt><dd>{task.search_id}</dd></div>
          <div><dt>Source platform</dt><dd>{task.request.source === 'linkedin' ? 'LinkedIn' : 'Wellfound'}</dd></div>
          <div><dt>Keyword</dt><dd>{task.request.keyword}</dd></div>
          <div><dt>Location</dt><dd>{task.request.location || 'All locations'}</dd></div>
          <div><dt>Posting date</dt><dd>{DATE_LABELS[task.request.date_posted]}</dd></div>
          <div><dt>Maximum results</dt><dd>{task.request.max_results}</dd></div>
          <div><dt>Created</dt><dd><time dateTime={task.created_at}>{time(task.created_at)}</time></dd></div>
          <div><dt>Last persisted update</dt><dd><time dateTime={latest.updated_at}>{time(latest.updated_at)}</time></dd></div>
        </dl>
      </section>
      <section className="card" aria-labelledby="activity-title">
        <div className="section-heading"><h2 id="activity-title">Live activity</h2><span>Latest 100 events · oldest first</span></div>
        <p className="search-note">Events are ordered by sequence. Event timestamps are not provided by the backend stream.</p>
        {progress.events.length === 0 ? <p className="notice">{historic ? 'This search was already finished when opened. Persisted counts are shown above; historical activity and page counts are unavailable here. For failed searches, intermediate progress counts are also unavailable because extracted jobs may never have been saved.' : 'No progress events received yet.'}</p> :
          <ol className="activity-list">{progress.events.map((event) => <li key={event.id}>
            <span className="event-sequence">#{event.id}</span><div><p>{activityMessage(event)}</p>
              <details><summary>Event details</summary><pre>{JSON.stringify(event.data, null, 2)}</pre></details>
            </div>
          </li>)}</ol>}
      </section>
      <section className="card" id="search-results" aria-labelledby="results-title">
        <h2 id="results-title">Job Results</h2>
        {!terminal ? <p className="notice">{progress.status === 'pending' ? 'Your search is queued.' : 'Your search is collecting jobs.'} Saved results will load when the search finishes. Live extraction events above are not saved job records.</p> : resultsError ? <><p role="alert" className="error-banner">Could not load persisted results: {resultsError}</p><button className="text-button" onClick={() => { setResultsError(''); setAttempt((n) => n + 1) }}>Reload results summary</button></> : results ?
          <><p className="notice">{results.total_extracted} qualifying jobs saved · {results.total_discovered} unique jobs discovered · {results.total_failed} extraction failures recorded.</p>
          {results.jobs.length === 0 && <p className="notice">{progress.status === 'failed' ? 'No saved jobs are available from this failed search.' : 'No jobs were saved for this search.'}</p>}
          {progress.status === 'failed' && results.jobs.length > 0 && <p className="notice">This search failed. Any saved results below may be incomplete.</p>}
          <JobResults jobs={results.jobs} searchId={task.search_id} /></> : <p role="status">Loading persisted results…</p>}
      </section>
      <Link className="text-link" to="/search">Back to Job Search</Link>
    </div>
  )
}

function LoadSearch({ searchId }: { searchId: string }) {
  const [task, setTask] = useState<SearchTask | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    getJobSearch(searchId, controller.signal).then((value) => {
      if (!controller.signal.aborted) setTask(value)
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setError(cause instanceof ApiError && cause.status === 404 ? 'Search not found.' : cause instanceof Error ? cause.message : 'Unable to load this search.')
    })
    return () => controller.abort()
  }, [searchId, attempt])
  if (error) return <section className="card"><p role="alert" className="error-banner">{error}</p><button className="text-button" onClick={() => { setError(''); setAttempt((n) => n + 1) }}>Reload search</button></section>
  if (!task) return <section className="card" role="status">Loading search…</section>
  return <SearchProgress task={task} />
}

export function SearchDetailsPage() {
  const { searchId } = useParams()
  return <>
    <PageHeader title="Search Details" description="Your search request, live progress, and saved job results." />
    {isSearchId(searchId) ? <LoadSearch key={searchId.toLowerCase()} searchId={searchId.toLowerCase()} /> :
      <section className="card"><p role="alert">Invalid search ID. Use the full search UUID from a created search.</p>{searchId && <p>{searchId}</p>}<Link className="text-link" to="/search">Back to Job Search</Link></section>}
  </>
}
