import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'
import { Icon } from '../components/ui/Icon'
import { PageHeader } from '../components/ui/PageHeader'
import { createJobSearch } from '../lib/api'
import { DATE_LABELS } from '../lib/search-contract'
import type { DatePosted, SearchSource } from '../types/search'

export function SearchPage() {
  const navigate = useNavigate()
  const [source, setSource] = useState<SearchSource>('careerhub')
  const [keyword, setKeyword] = useState('')
  const [location, setLocation] = useState('')
  const [datePosted, setDatePosted] = useState<DatePosted>('any')
  const [maxResults, setMaxResults] = useState('20')
  const [watchMode, setWatchMode] = useState(true)
  const [watchDelay, setWatchDelay] = useState('2')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const request = useRef<AbortController | null>(null)
  useEffect(() => () => request.current?.abort(), [])

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (request.current) return
    const next: Record<string, string> = {}
    const trimmedKeyword = keyword.trim()
    const trimmedLocation = location.trim()
    if (!trimmedKeyword) next.keyword = 'Enter a job title or keyword.'
    else if (keyword.length > 200) next.keyword = 'Use 200 characters or fewer.'
    if (location.length > 200) next.location = 'Use 200 characters or fewer.'
    const limit = Number(maxResults)
    if (!maxResults.trim() || !Number.isInteger(limit) || limit < 1 || limit > 500) {
      next.maxResults = 'Enter a whole number from 1 to 500.'
    }
    setErrors(next)
    setError('')
    if (Object.keys(next).length) return
    const controller = new AbortController()
    request.current = controller
    setPending(true)
    try {
      const response = await createJobSearch({ source, keyword: trimmedKeyword, location: trimmedLocation,
        date_posted: datePosted, max_results: limit, watch_mode: watchMode, watch_delay_seconds: Number(watchDelay) }, controller.signal)
      if (!controller.signal.aborted) navigate(`/searches/${response.search_id}`)
    } catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Search submission failed.')
    } finally {
      request.current = null
      if (!controller.signal.aborted) setPending(false)
    }
  }

  return (
    <>
      <PageHeader title="Job Search" eyebrow="DISCOVER YOUR NEXT MOVE"
        description="Choose a source and shape your search. Follow real progress as a worker collects qualifying jobs." />
      <div className="source-grid">
        <article className="card source-card"><h3>CareerHub</h3><p>Visible browser search of public South African listings.</p></article>
        <article className="card source-card"><h3>LinkedIn</h3><p>User-assisted search and saving.</p></article>
        <article className="card source-card"><h3>Wellfound</h3><p>User-assisted search and saving.</p></article>
      </div>
      <p className="notice">CareerHub: visible automated search of public South African listings (up to 20 detail visits). LinkedIn and Wellfound: Chrome opens for you to search manually, then paste jobs into ScrapLink. No automated collection on restricted sites.</p>
      <section className="card search-form-card" aria-labelledby="search-builder-title">
        <h2 id="search-builder-title">Set your direction</h2>
        <form onSubmit={submit} noValidate aria-busy={pending}>
          <fieldset disabled={pending} className="form-grid">
            <div className="form-field">
              <label htmlFor="source">Job source</label>
              <select id="source" value={source} onChange={(e) => { setSource(e.target.value as SearchSource); setErrors({}) }}>
                <option value="careerhub">CareerHub — visible browser</option><option value="linkedin">LinkedIn — user assisted</option><option value="wellfound">Wellfound — user assisted</option>
              </select>
            </div>
            <div className="form-field">
              <label htmlFor="keyword">Job title / keyword <span>(required)</span></label>
              <input id="keyword" required value={keyword} placeholder="Senior Software Engineer"
                aria-invalid={!!errors.keyword} aria-describedby="keyword-help keyword-error"
                onChange={(e) => setKeyword(e.target.value)} />
              <small id="keyword-help">Any job title or keyword, up to 200 characters. Your wording is preserved.</small>
              <span id="keyword-error" className="field-error">{errors.keyword}</span>
            </div>
            <div className="form-field">
              <label htmlFor="location">Location</label>
              <input id="location" value={location}
                aria-invalid={!!errors.location} aria-describedby="location-help location-error" onChange={(e) => setLocation(e.target.value)} />
              <small id="location-help">{source === 'careerhub' ? 'CareerHub has no location input. ScrapLink filters the location text after inspecting listings. Leave empty for all.' : 'Enter this location in the website yourself. Leave empty for all.'}</small>
              <span id="location-error" className="field-error">{errors.location}</span>
            </div>
            <div className="form-field">
              <label htmlFor="date-posted">Posting date</label>
              <select id="date-posted" value={datePosted} onChange={(e) => setDatePosted(e.target.value as DatePosted)} aria-describedby="date-help">
                {Object.entries(DATE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
              <small id="date-help">CareerHub does not publish posting dates; choose Any time to include those jobs. With a date filter, jobs without verifiable posting dates may be excluded. Exclusions are not extraction failures.</small>
            </div>
            <div className="form-field">
              <label htmlFor="max-results">Maximum results</label>
              <input id="max-results" type="number" min="1" max="500" step="1" value={maxResults}
                aria-invalid={!!errors.maxResults} aria-describedby="max-help max-error" onChange={(e) => setMaxResults(e.target.value)} />
              <small id="max-help">1–500 qualifying jobs. The search may find fewer.</small>
              <span id="max-error" className="field-error">{errors.maxResults}</span>
            </div>
            <div className="form-field">
              <label htmlFor="watch-mode"><input id="watch-mode" type="checkbox" checked={watchMode} onChange={(e) => setWatchMode(e.target.checked)} /> Watch mode</label>
              <label htmlFor="watch-delay">Pause between actions</label>
              <select id="watch-delay" value={watchDelay} onChange={(e) => setWatchDelay(e.target.value)}>
                <option value="1.5">1.5 seconds</option><option value="2">2 seconds</option><option value="3">3 seconds</option>
              </select>
              <small>Watch mode keeps Chrome visible and types one character at a time.</small>
            </div>
          </fieldset>
          <p className="search-note">An active local worker opens Chrome after claiming your search. Live mode uses real websites only. Access challenges stop collection and appear as failures; no login or CAPTCHA bypass is attempted.</p>
          {error && <p className="error-banner" role="alert">{error}</p>}
          <button type="submit" className="button button-primary" disabled={pending}>
            {pending ? <><span className="loading-spinner" aria-hidden="true" />Creating search…</> : <>Start Search<Icon name="arrow" /></>}
          </button>
        </form>
      </section>
    </>
  )
}
