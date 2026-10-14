import { useCallback, useEffect, useRef, useState } from 'react'

type Job = {
  id: string; title: string; company: string; location: string | null
  workplace_type: string | null; employment_type: string | null
  compensation: { raw_text: string | null } | null
  posted_date: string; posted_at: string | null; posted_text: string | null
  description: string | null; source: string; job_url: string
}
type Source = { source: string; status: string; scanned: number; saved: number; undated: number; error: string | null }
type Run = { search_id: string; status: string; saved: number; sources: Record<string, Source>; error: string | null }
type Dashboard = { jobs: Job[]; run: Run | null; worker_available: boolean }

const names: Record<string, string> = { ashby: 'Ashby', greenhouse: 'Greenhouse', lever: 'Lever', remotive: 'Remotive', usajobs: 'USAJOBS' }
const active = (run: Run | null) => run?.status === 'pending' || run?.status === 'running'

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  let response: Response
  try { response = await fetch(url, options) }
  catch { throw new Error('Cannot reach ScrapLink. Check that the local application is running.') }
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? `Server returned HTTP ${response.status}. Check the application terminal for the cause.`)
  }
  return response.json()
}

function originalUrl(value: string) {
  try { const url = new URL(value); return url.protocol === 'https:' && !url.username && !url.password ? url.href : null }
  catch { return null }
}

export function DashboardPage() {
  const [data, setData] = useState<Dashboard>({ jobs: [], run: null, worker_available: true })
  const [loading, setLoading] = useState(true)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState('')
  const [streamError, setStreamError] = useState('')
  const inFlight = useRef(false)
  const mounted = useRef(false)
  const refresh = useCallback(async () => {
    // Coalesce overlapping SSE events; periodic refresh also catches events during a read.
    if (inFlight.current) return
    inFlight.current = true
    try {
      const next = await request<Dashboard>('/api/v1/jobs')
      if (mounted.current) { setData(next); setError('') }
    } catch (e) { if (mounted.current) setError((e as Error).message) }
    finally { inFlight.current = false; if (mounted.current) setLoading(false) }
  }, [])

  useEffect(() => {
    mounted.current = true
    const initial = window.setTimeout(() => void refresh(), 0)
    const timer = window.setInterval(() => void refresh(), 3000)
    return () => { mounted.current = false; window.clearTimeout(initial); window.clearInterval(timer) }
  }, [refresh])

  const runId = data.run?.search_id
  const running = active(data.run)
  useEffect(() => {
    if (!runId || !running) return
    const stream = new EventSource(`/api/v1/jobs/search/${runId}/events`)
    const update = () => { setStreamError(''); void refresh() }
    for (const name of ['search_queued', 'search_started', 'source_status', 'job_saved']) stream.addEventListener(name, update)
    const finish = () => { stream.close(); update() }
    stream.addEventListener('search_completed', finish)
    stream.addEventListener('search_failed', finish)
    stream.onerror = () => setStreamError('Live updates disconnected. Reconnecting; saved results are still checked every three seconds.')
    return () => stream.close()
  }, [runId, running, refresh])

  async function start() {
    if (starting || running) return
    setStarting(true); setError(''); setStreamError('')
    try {
      const run = await request<Run>('/api/v1/jobs/search', { method: 'POST' })
      setData(previous => ({ ...previous, run }))
    } catch (e) { setError((e as Error).message) }
    finally { setStarting(false) }
  }

  return (
    <main>
      <header><a className="brand" href="/">ScrapLink<span>PUBLIC JOB DISCOVERY</span></a><span className="local-label">Your job dashboard</span></header>
      <section className="intro">
        <div><p className="eyebrow">A fresh place to start</p><h1>Find your next opportunity.</h1><p>Discover jobs published in the last 7 days.<br />Verified dates. Original postings. Saved automatically.</p></div>
        <button onClick={() => void start()} disabled={loading || starting || running}>{starting ? 'Starting…' : running ? 'Searching…' : 'Search Jobs'}<span aria-hidden="true"> ↗</span></button>
      </section>
      {error && <p className="error" role="alert">{error}</p>}
      {!data.worker_available && !loading && <p className="error" role="status">Discovery worker is offline. Start the application with its local startup command.</p>}
      {streamError && running && <p role="status">{streamError}</p>}
      {data.run && <section className="progress" aria-label="Search progress">
        <div className="section-heading"><h2>{running ? 'Discovering jobs' : data.run.status === 'failed' ? 'Search interrupted' : 'Search finished'}</h2><span>{data.run.saved} saved this run</span></div>
        <p role="status">{data.run.status === 'pending' ? 'Queued — waiting for the worker.' : running ? 'Checking public sources and saving verified jobs as they arrive.' : 'Saved jobs remain here when you return.'}</p>
        {data.run.error && <p className="error">{data.run.error}</p>}
        <div className="sources">{Object.entries(names).map(([key, name]) => {
          const source = data.run?.sources[key]
          return <div className="source" key={key}><strong>{name}</strong><span>{source ? `${source.status.replaceAll('_', ' ')} · ${source.saved} saved · ${source.scanned} checked` : running ? 'Waiting' : 'Not run'}</span>{!!source?.undated && <small>{source.undated} without verifiable dates</small>}{source?.error && <small className="error">{source.error}</small>}</div>
        })}</div>
      </section>}
      <section aria-label="Saved jobs">
        <div className="section-heading"><h2>Saved jobs <span className="count">{data.jobs.length}</span></h2><span>Newest published first</span></div>
        {loading ? <p role="status">Loading saved jobs…</p> : !data.jobs.length ? <div className="empty"><h3>Your next chapter starts here.</h3><p>{running ? 'Checking publication dates. Qualifying jobs will appear here as they are saved.' : 'Click Search Jobs to discover recent openings across public job boards.'}</p></div> : <div className="jobs">{data.jobs.map(job => {
          const url = originalUrl(job.job_url)
          return <article className="job" key={job.id}>
            <div className="job-top"><span className="source-name">{names[job.source] ?? job.source}</span><time dateTime={job.posted_at ?? job.posted_date}>{job.posted_at ? new Date(job.posted_at).toLocaleString() : job.posted_date}</time></div>
            <h3>{job.title}</h3><p className="company">{job.company || 'Company unknown'}</p>
            <dl><div><dt>Location</dt><dd>{job.location || 'Unknown'}</dd></div><div><dt>Work type</dt><dd>{[job.workplace_type, job.employment_type].filter(Boolean).map(v => v!.replaceAll('_', ' ')).join(' · ') || 'Unknown'}</dd></div><div><dt>Salary</dt><dd>{job.compensation?.raw_text || 'Unknown'}</dd></div></dl>
            <details><summary>Full description</summary><p className="description">{job.description || 'Unknown'}</p><p className="evidence">Publication evidence: {job.posted_text || 'Unknown'}</p></details>
            {url && <a className="original" href={url} target="_blank" rel="noopener noreferrer">View original posting ↗<span>{url}</span></a>}
          </article>
        })}</div>}
      </section>
      <footer>Public employer boards and permitted job feeds. Up to 20 recent jobs per source.<br />Limited board coverage; unavailable or undated listings are excluded.</footer>
    </main>
  )
}
