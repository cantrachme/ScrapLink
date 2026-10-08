import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'
import { Icon } from '../components/ui/Icon'
import { PageHeader } from '../components/ui/PageHeader'
import { createJobSearch } from '../lib/api'
import { DATE_LABELS, WELLFOUND_LOCATIONS, WELLFOUND_ROLES } from '../lib/search-contract'
import type { DatePosted, SearchSource } from '../types/search'

export function SearchPage() {
  const navigate = useNavigate()
  const [source, setSource] = useState<SearchSource>('linkedin')
  const [keyword, setKeyword] = useState('')
  const [location, setLocation] = useState('United States')
  const [datePosted, setDatePosted] = useState<DatePosted>('24h')
  const [maxResults, setMaxResults] = useState('20')
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
    if (source === 'wellfound') {
      if (trimmedKeyword && !WELLFOUND_ROLES.some((role) => role.toLowerCase() === trimmedKeyword.toLowerCase())) {
        next.keyword = `Wellfound supports only: ${WELLFOUND_ROLES.join(', ')}.`
      }
      if (trimmedLocation && !WELLFOUND_LOCATIONS.some((place) => place.toLowerCase() === trimmedLocation.toLowerCase())) {
        next.location = 'Wellfound supports United States, New York, or an empty location for all locations.'
      }
    }
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
        date_posted: datePosted, max_results: limit }, controller.signal)
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
        <article className="card source-card"><h3>LinkedIn</h3><p>Professional roles across companies, industries, and locations.</p></article>
        <article className="card source-card"><h3>Wellfound</h3><p>Startup opportunities through supported public role and location pages.</p></article>
      </div>
      <section className="card search-form-card" aria-labelledby="search-builder-title">
        <h2 id="search-builder-title">Set your direction</h2>
        <form onSubmit={submit} noValidate aria-busy={pending}>
          <fieldset disabled={pending} className="form-grid">
            <div className="form-field">
              <label htmlFor="source">Job source</label>
              <select id="source" value={source} onChange={(e) => { setSource(e.target.value as SearchSource); setErrors({}) }}>
                <option value="linkedin">LinkedIn</option><option value="wellfound">Wellfound</option>
              </select>
            </div>
            <div className="form-field">
              <label htmlFor="keyword">Job title / keyword <span>(required)</span></label>
              <input id="keyword" required value={keyword} placeholder="Senior Software Engineer"
                list={source === 'wellfound' ? 'wellfound-roles' : undefined}
                aria-invalid={!!errors.keyword} aria-describedby="keyword-help keyword-error"
                onChange={(e) => setKeyword(e.target.value)} />
              <small id="keyword-help">{source === 'wellfound' ? `Supported roles only: ${WELLFOUND_ROLES.join(', ')}.` : 'Up to 200 characters.'}</small>
              <span id="keyword-error" className="field-error">{errors.keyword}</span>
              <datalist id="wellfound-roles">{WELLFOUND_ROLES.map((role) => <option key={role} value={role} />)}</datalist>
            </div>
            <div className="form-field">
              <label htmlFor="location">Location</label>
              <input id="location" value={location} list={source === 'wellfound' ? 'wellfound-locations' : undefined}
                aria-invalid={!!errors.location} aria-describedby="location-help location-error" onChange={(e) => setLocation(e.target.value)} />
              <small id="location-help">{source === 'wellfound' ? 'United States or New York. Leave empty for all locations.' : 'Leave empty for all locations. Up to 200 characters.'}</small>
              <span id="location-error" className="field-error">{errors.location}</span>
              <datalist id="wellfound-locations">{WELLFOUND_LOCATIONS.map((place) => <option key={place} value={place} />)}</datalist>
            </div>
            <div className="form-field">
              <label htmlFor="date-posted">Posting date</label>
              <select id="date-posted" value={datePosted} onChange={(e) => setDatePosted(e.target.value as DatePosted)} aria-describedby="date-help">
                {Object.entries(DATE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
              <small id="date-help">{source === 'wellfound' ? 'Wellfound dates are filtered after extraction. ' : ''}With a date filter, jobs without verifiable posting dates may be excluded. Exclusions are not extraction failures.</small>
            </div>
            <div className="form-field">
              <label htmlFor="max-results">Maximum results</label>
              <input id="max-results" type="number" min="1" max="500" step="1" value={maxResults}
                aria-invalid={!!errors.maxResults} aria-describedby="max-help max-error" onChange={(e) => setMaxResults(e.target.value)} />
              <small id="max-help">1–500 qualifying jobs. The search may find fewer.</small>
              <span id="max-error" className="field-error">{errors.maxResults}</span>
            </div>
          </fieldset>
          <p className="search-note">Searches enter a queue and require an active worker. Submitting this form does not launch Chrome. Worker startup integration is planned for Step 50.</p>
          {error && <p className="error-banner" role="alert">{error}</p>}
          <button type="submit" className="button button-primary" disabled={pending}>
            {pending ? <><span className="loading-spinner" aria-hidden="true" />Creating search…</> : <>Start Search<Icon name="arrow" /></>}
          </button>
        </form>
      </section>
    </>
  )
}
