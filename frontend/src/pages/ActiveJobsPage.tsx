import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { PageHeader } from '../components/ui/PageHeader'
import { ActiveJobsButton } from '../components/jobs/ActiveJobsButton'
import { ACTIVE_OPTIONS_KEY, readActiveOptions } from '../lib/active-options'
import { AssistedJobForm } from '../components/jobs/AssistedJobForm'
import { JobResults } from '../components/jobs/JobResults'
import { useSearchEvents } from '../hooks/useSearchEvents'
import { getJobSearch, getSearchResults } from '../lib/api'
import { isSearchId } from '../lib/search-contract'
import { activityMessage } from '../lib/search-events'
import type { JobSearchResultsResponse, SearchTask } from '../types/search'

const sourceNames: Record<string, string> = { linkedin: 'LinkedIn', wellfound: 'Wellfound' }
const sourceStates: Record<string, string> = {
  collecting: 'Opening Chrome and checking access…', completed: 'Discovery finished',
  authorization_required: 'Automated discovery is not authorized. Chrome is open for manual browsing; save permitted details below.',
  access_blocked: 'Login, CAPTCHA, or a platform restriction stopped collection. Use manual browsing and permitted entry.',
  failed: 'Source could not be inspected. Other saved results are retained. You can save permitted details below.',
  limit_reached: 'The shared maximum result count has been reached.',
}

function ActiveResults({ task }: { task: SearchTask }) {
  const progress = useSearchEvents(task, true)
  const [results, setResults] = useState<JobSearchResultsResponse | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const revision = progress.events.filter((e) => ['job_saved', 'source_status', 'job_failed'].includes(e.event)).at(-1)?.id
  useEffect(() => {
    const controller = new AbortController()
    getSearchResults(task.search_id, controller.signal).then((value) => {
      if (!controller.signal.aborted) { setResults(value); setError('') }
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Could not load saved jobs.')
    })
    return () => controller.abort()
  }, [task.search_id, revision, progress.status, progress.connection, attempt])
  const sourceStatuses = { ...results?.source_statuses }
  for (const event of progress.events) {
    if (event.event === 'source_status') sourceStatuses[event.data.source] = event.data.status
  }
  return <div className="search-details-stack">
    <section className="card">
      <h2>Discovery · {progress.status}</h2>
      <p role="status">{progress.status === 'pending' ? 'Queued — waiting for the existing worker to open Chrome.' : `Live connection: ${progress.connection}`}</p>
      <p>Both sources · no title or location filter · maximum {task.request.max_results} saved jobs. Automated collection accepts posting evidence within the last 24 hours. Availability remains unknown unless verified; the page name is not an active-status guarantee.</p>
      <ul>{Object.entries(sourceNames).map(([source, name]) => <li key={source}><strong>{name}:</strong> {sourceStates[sourceStatuses[source]] || 'Waiting to start'}</li>)}</ul>
      {progress.error && <p role="alert" className="error-banner">{progress.error}. Previously saved jobs are retained.</p>}
      {progress.warning && <p role="alert">{progress.warning}</p>}
      {results?.failures.map((failure, i) => <p key={i} className="notice">{sourceNames[failure.source || ''] || 'Listing'}: {failure.error}</p>)}
    </section>
    <section className="card" aria-label="Active Jobs results">
      <h2>Saved jobs · {results?.jobs.length ?? 0}</h2>
      <p>Jobs appear as each save completes. Unknown fields stay unspecified. User-supplied jobs may have unknown or older dates and are not independently verified.</p>
      {error && <p role="alert" className="error-banner">{error}</p>}
      <button className="text-button" onClick={() => setAttempt((n) => n + 1)}>Refresh saved jobs</button>
      {!results && !error && <p role="status">Loading saved jobs…</p>}
      {results && !results.jobs.length && <p>No jobs saved yet. No demonstration jobs are shown.</p>}
      {results && <JobResults jobs={results.jobs} searchId={task.search_id} active />}
    </section>
    {progress.status !== 'pending' && <AssistedJobForm task={task} onSaved={() => setAttempt((n) => n + 1)} />}
    <section className="card"><h2>Browser activity</h2>
      {!progress.events.length && <p>Live actions will appear here while this task runs.</p>}
      <ol className="activity-list">{progress.events.map((event) => <li key={event.id}>{activityMessage(event)}</li>)}</ol>
    </section>
  </div>
}

function LoadActiveJobs({ searchId }: { searchId: string }) {
  const [task, setTask] = useState<SearchTask | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    getJobSearch(searchId, controller.signal).then((value) => {
      if (!controller.signal.aborted) {
        if (value.request.mode !== 'active_jobs') setError('This task is not an Active Jobs discovery.')
        else { setTask(value); setError('') }
      }
    }).catch((cause: unknown) => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Could not load discovery.') })
    return () => controller.abort()
  }, [searchId, attempt])
  if (error) return <section className="card"><p role="alert">{error}</p><button onClick={() => setAttempt((n) => n + 1)}>Retry loading discovery</button></section>
  return task ? <ActiveResults task={task} /> : <p role="status">Loading discovery…</p>
}

export function ActiveJobsPage() {
  const { searchId } = useParams()
  const [options, setOptions] = useState(readActiveOptions)
  function update(next: typeof options) {
    setOptions(next)
    try { localStorage.setItem(ACTIVE_OPTIONS_KEY, JSON.stringify(next)) } catch { /* Current form still works. */ }
  }
  return <>
    <PageHeader title="Active Jobs" description="LinkedIn and Wellfound in one live dashboard, with evidence-based posting dates and original links." />
    <section className="card">
      <h2>Discovery settings</h2>
      <div className="form-grid">
        <div className="form-field"><label htmlFor="active-max">Maximum results across both sources</label><input id="active-max" type="number" min={1} max={500} value={options.max_results} onChange={(e) => update({ ...options, max_results: Math.max(1, Math.min(500, Math.trunc(Number(e.target.value)))) })} /></div>
        <div className="form-field"><label htmlFor="active-watch"><input id="active-watch" type="checkbox" checked={options.watch_mode} onChange={(e) => update({ ...options, watch_mode: e.target.checked })} /> Watch mode</label></div>
        <div className="form-field"><label htmlFor="active-delay">Watch delay (seconds)</label><select id="active-delay" value={options.watch_delay_seconds} onChange={(e) => update({ ...options, watch_delay_seconds: Number(e.target.value) })}>{[1.5, 2, 2.5, 3].map((value) => <option key={value}>{value}</option>)}</select></div>
      </div>
      <p>Chrome stays visible. Settings apply to the next discovery. Each source requires platform authorization for automated collection; otherwise Chrome opens for manual browsing.</p>
      <ActiveJobsButton options={options} label="Start new discovery" />
    </section>
    {searchId ? isSearchId(searchId) ? <LoadActiveJobs key={searchId} searchId={searchId} /> : <p role="alert">Invalid discovery ID.</p> : <p>Start discovery to open both sources without a required keyword or location.</p>}
    <Link className="text-link" to="/search">Job Search</Link>
  </>
}
