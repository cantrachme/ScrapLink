import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { PageHeader } from '../components/ui/PageHeader'
import { ExternalJobLink } from '../components/jobs/ExternalJobLink'
import { ApiError, getJobById } from '../lib/api'
import { isSearchId } from '../lib/search-contract'
import { EMPLOYMENT_LABELS, SOURCE_LABELS, WORKPLACE_LABELS } from '../lib/job-contract'
import { descriptionText, formatCompensation, formatDate, NOT_SPECIFIED, postingDate, safeExternalUrl, textOrFallback } from '../lib/job-format'
import type { PersistedJob } from '../types/job'

function JobContent({ job }: { job: PersistedJob }) {
  const compensation = formatCompensation(job.compensation)
  const description = job.description ? descriptionText(job.description) : ''
  const metadata = [
    ['Company', job.company], ['Source platform', SOURCE_LABELS[job.source]],
    ['Location', textOrFallback(job.location)], ['Workplace type', job.workplace_type ? WORKPLACE_LABELS[job.workplace_type] : NOT_SPECIFIED],
    ['Employment type', job.employment_type ? EMPLOYMENT_LABELS[job.employment_type] : NOT_SPECIFIED],
    ['Seniority level', textOrFallback(job.seniority_level)], ['Job status', job.status === 'unknown' ? 'Unknown' : job.status === 'active' ? 'Active' : 'Closed'],
    ['Posting date', formatDate(postingDate(job))],
    ...(job.posted_text ? [['Source posting text', job.posted_text]] : []),
    ['First discovered', formatDate(job.first_seen_at, true)], ['Last verified', formatDate(job.last_verified_at, true)],
    ['Last updated', formatDate(job.updated_at, true)],
    ...(job.source_job_id ? [['Source job ID', job.source_job_id]] : []),
  ]
  return <article className="job-details-stack">
    <section className="card job-overview" aria-labelledby="job-title">
      <p className="eyebrow">{SOURCE_LABELS[job.source]}</p><h2 id="job-title">{job.title}</h2><p className="job-company">{job.company}</p>
      <div className="job-actions"><ExternalJobLink url={job.job_url}>Open original listing</ExternalJobLink><ExternalJobLink url={job.application_url}>Open application link</ExternalJobLink></div>
      <dl className="request-summary">{metadata.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
    </section>
    <section className="card job-prose" aria-labelledby="description-title"><h2 id="description-title">Job description</h2><p className="job-description">{description || 'No description was provided for this job.'}</p></section>
    {([['Responsibilities', job.responsibilities], ['Requirements', job.requirements], ['Skills', job.skills]] as const).map(([heading, items]) => items.length > 0 &&
      <section key={heading} className="card job-prose" aria-label={heading}><h2>{heading}</h2><ul>{items.map((item, index) => <li key={index}>{descriptionText(item)}</li>)}</ul></section>)}
    {(job.experience_min_years !== null || job.experience_max_years !== null) && <section className="card job-prose" aria-label="Experience"><h2>Experience</h2><dl className="request-summary">
      {job.experience_min_years !== null && <div><dt>Minimum experience</dt><dd>{job.experience_min_years} years</dd></div>}
      {job.experience_max_years !== null && <div><dt>Maximum experience</dt><dd>{job.experience_max_years} years</dd></div>}
    </dl></section>}
    {(compensation || job.compensation?.raw_text) && <section className="card job-prose" aria-label="Compensation"><h2>Compensation</h2>{compensation && <p>{compensation}</p>}{job.compensation?.raw_text && <p className="job-description">{job.compensation.raw_text}</p>}</section>}
    <section className="card job-prose" aria-label="Source links"><h2>Source links</h2><dl className="request-summary">
      {([['Original job URL', job.job_url], ['Application URL', job.application_url], ['Company URL', job.company_url]] as const).map(([label, url]) => url && <div key={label}><dt>{label}</dt><dd>{safeExternalUrl(url) ? <ExternalJobLink url={url}>{url}</ExternalJobLink> : 'Link unavailable'}</dd></div>)}
    </dl><p className="search-note">Only valid HTTP and HTTPS links can be opened. Listing details reflect the last stored information.</p></section>
  </article>
}

function LoadJob({ jobId }: { jobId: string }) {
  const [job, setJob] = useState<PersistedJob | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    getJobById(jobId, controller.signal).then((value) => {
      if (!controller.signal.aborted) setJob(value)
    }).catch((cause: unknown) => {
      if (controller.signal.aborted) return
      setError(cause instanceof ApiError && cause.status === 404 ? 'Job not found. This saved job may no longer be available.' :
        cause instanceof ApiError && cause.status === 422 ? 'The backend rejected this job ID.' : cause instanceof Error ? cause.message : 'Unable to load this job.')
    })
    return () => controller.abort()
  }, [jobId, attempt])
  if (error) return <section className="card"><p className="error-banner" role="alert">{error}</p><button className="text-button" onClick={() => { setError(''); setAttempt((n) => n + 1) }}>Reload job</button></section>
  if (!job) return <section className="card" role="status">Loading job details…</section>
  return <JobContent job={job} />
}

export function JobDetailsPage() {
  const { jobId } = useParams()
  const [params] = useSearchParams()
  const searchId = params.get('searchId')
  return <>
    <PageHeader title="Job Details" description="Get to know an opportunity beyond its title." />
    <div className="job-back-link">{isSearchId(searchId) ? <Link className="text-link" to={`/searches/${searchId.toLowerCase()}`}>Back to search results</Link> : <Link className="text-link" to="/search">Back to Job Search</Link>}</div>
    {isSearchId(jobId) ? <LoadJob key={jobId.toLowerCase()} jobId={jobId.toLowerCase()} /> : <section className="card"><p role="alert">Invalid job ID. Use the full saved job UUID.</p>{jobId && <p>{jobId}</p>}</section>}
  </>
}
