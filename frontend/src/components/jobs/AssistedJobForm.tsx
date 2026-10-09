import { useState, type FormEvent } from 'react'
import { requestJson, API_PATHS } from '../../lib/api'
import type { SearchTask } from '../../types/search'

export function AssistedJobForm({ task, onSaved }: { task: SearchTask, onSaved: () => void }) {
  const active = task.request.mode === 'active_jobs'
  const [source, setSource] = useState('linkedin')
  const [company, setCompany] = useState('')
  const [salary, setSalary] = useState('')
  const [posted, setPosted] = useState('')
  const [postedText, setPostedText] = useState('')
  const [title, setTitle] = useState('')
  const [url, setUrl] = useState('')
  const [location, setLocation] = useState('')
  const [workplace, setWorkplace] = useState('')
  const [description, setDescription] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  async function save(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    setBusy(true); setMessage('')
    try {
      await requestJson(`${API_PATHS.search(task.search_id)}/assisted-jobs`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...(active ? { source, company, compensation: salary ? { raw_text: salary } : null,
          posted_date: posted || null, posted_text: postedText || null } : {}), title: title.trim(), job_url: url.trim(), location: location || null,
          workplace_type: workplace || null, description: description || null }),
      })
      setMessage('Job saved. It is available in your results below.')
      setTitle(''); setUrl(''); setDescription(''); setLocation(''); setWorkplace('')
      setCompany(''); setSalary(''); setPosted(''); setPostedText('')
      onSaved()
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Unable to save job') }
    finally { setBusy(false) }
  }
  return <section className="card">
    <h2>Save a job from your browser</h2>
    {active ? <p>Browse either source in Chrome without a required role or location. Copy only details you can access and are permitted to save. These entries are user supplied; posting dates and availability are not independently verified.</p> : <p>In Chrome, search for <strong>{task.request.keyword}</strong>{task.request.location && <> in <strong>{task.request.location}</strong></>}. Open a listing and copy its title and original URL below. These are user-supplied details; ScrapLink does not fetch or verify the restricted page.</p>}
    <form onSubmit={save}>
      <fieldset className="form-grid" disabled={busy}>
        {active && <>
          <div className="form-field"><label htmlFor="save-source">Listing source</label><select id="save-source" value={source} onChange={(e) => setSource(e.target.value)}><option value="linkedin">LinkedIn</option><option value="wellfound">Wellfound</option></select></div>
          <div className="form-field"><label htmlFor="save-company">Company (optional)</label><input id="save-company" maxLength={500} value={company} onChange={(e) => setCompany(e.target.value)} /></div>
          <div className="form-field"><label htmlFor="save-salary">Salary as published (optional)</label><input id="save-salary" value={salary} onChange={(e) => setSalary(e.target.value)} /></div>
          <div className="form-field"><label htmlFor="save-posted">Published date (optional)</label><input id="save-posted" type="date" value={posted} onChange={(e) => setPosted(e.target.value)} /></div>
          <div className="form-field"><label htmlFor="save-posted-text">Posting date evidence (optional)</label><input id="save-posted-text" maxLength={255} value={postedText} onChange={(e) => setPostedText(e.target.value)} /></div>
        </>}
        <div className="form-field"><label htmlFor="save-title">Job title to save</label><input id="save-title" required maxLength={500} value={title} onChange={(e) => setTitle(e.target.value)} /></div>
        <div className="form-field"><label htmlFor="save-url">Original job URL</label><input id="save-url" required type="url" value={url} onChange={(e) => setUrl(e.target.value)} /></div>
        <div className="form-field"><label htmlFor="save-location">Job location (optional)</label><input id="save-location" value={location} onChange={(e) => setLocation(e.target.value)} /></div>
        <div className="form-field"><label htmlFor="save-workplace">Work type (optional)</label><select id="save-workplace" value={workplace} onChange={(e) => setWorkplace(e.target.value)}><option value="">Unknown</option><option value="remote">Remote</option><option value="hybrid">Hybrid</option><option value="onsite">On-site</option></select></div>
        <div className="form-field"><label htmlFor="save-description">Description (optional)</label><textarea id="save-description" value={description} onChange={(e) => setDescription(e.target.value)} /></div>
      </fieldset>
      <button className="button button-primary" disabled={busy} type="submit">{busy ? 'Saving…' : 'Save job'}</button>
      {message && <p role="status">{message}</p>}
    </form>
  </section>
}
