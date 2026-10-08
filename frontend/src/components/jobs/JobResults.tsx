import { useMemo, useState } from 'react'
import { Link } from 'react-router'
import type { PersistedJob } from '../../types/job'
import { EMPLOYMENT_LABELS, SOURCE_LABELS, WORKPLACE_LABELS } from '../../lib/job-contract'
import { dateValue, formatDate, NOT_SPECIFIED, postingDate, textOrFallback } from '../../lib/job-format'
import { ExternalJobLink } from './ExternalJobLink'

export function JobResults({ jobs, searchId }: { jobs: PersistedJob[]; searchId: string }) {
  const [title, setTitle] = useState('')
  const [company, setCompany] = useState('')
  const [source, setSource] = useState('')
  const [workplace, setWorkplace] = useState('')
  const [employment, setEmployment] = useState('')
  const [sort, setSort] = useState('newest')
  const [pageSize, setPageSize] = useState(20)
  const [page, setPage] = useState(1)
  const loaded = useMemo(() => [...new Map(jobs.map((job) => [job.id.toLowerCase(), job])).values()], [jobs])
  const sources = [...new Set(loaded.map((job) => job.source))].sort()
  const workplaces = [...new Set(loaded.flatMap((job) => job.workplace_type ? [job.workplace_type] : []))].sort()
  const employments = [...new Set(loaded.flatMap((job) => job.employment_type ? [job.employment_type] : []))].sort()
  const filtered = useMemo(() => loaded.filter((job) =>
    job.title.toLowerCase().includes(title.trim().toLowerCase()) &&
    job.company.toLowerCase().includes(company.trim().toLowerCase()) &&
    (!source || job.source === source) && (!workplace || job.workplace_type === workplace) &&
    (!employment || job.employment_type === employment),
  ).sort((a, b) => {
    let comparison: number
    if (sort === 'title' || sort === 'company') comparison = a[sort].localeCompare(b[sort], undefined, { sensitivity: 'base' })
    else {
      const first = dateValue(postingDate(a)), second = dateValue(postingDate(b))
      // Unknown dates always follow verifiable dates in either direction.
      comparison = first === null ? second === null ? 0 : 1 : second === null ? -1 :
        sort === 'oldest' ? first - second : second - first
    }
    return comparison || a.id.localeCompare(b.id)
  }), [loaded, title, company, source, workplace, employment, sort])
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize))
  const currentPage = Math.min(page, pages)
  const offset = (currentPage - 1) * pageSize
  const visible = filtered.slice(offset, offset + pageSize)
  function change(setter: (value: string) => void, value: string) { setter(value); setPage(1) }
  const detailUrl = (id: string) => `/jobs/${id}?searchId=${encodeURIComponent(searchId)}`
  return <>
    <p className="search-note">{loaded.length} loaded jobs. Filters and pages apply to this search’s saved results.</p>
    {loaded.length > 0 && <>
      <div className="results-controls">
        <div className="form-field"><label htmlFor="filter-title">Search job titles</label><input id="filter-title" type="search" value={title} onChange={(e) => change(setTitle, e.target.value)} /></div>
        <div className="form-field"><label htmlFor="filter-company">Search companies</label><input id="filter-company" type="search" value={company} onChange={(e) => change(setCompany, e.target.value)} /></div>
        {sources.length > 1 && <div className="form-field"><label htmlFor="filter-source">Source</label><select id="filter-source" value={source} onChange={(e) => change(setSource, e.target.value)}><option value="">All sources</option>{sources.map((v) => <option key={v} value={v}>{SOURCE_LABELS[v]}</option>)}</select></div>}
        {workplaces.length > 0 && <div className="form-field"><label htmlFor="filter-workplace">Workplace type</label><select id="filter-workplace" value={workplace} onChange={(e) => change(setWorkplace, e.target.value)}><option value="">All workplaces</option>{workplaces.map((v) => <option key={v} value={v}>{WORKPLACE_LABELS[v]}</option>)}</select></div>}
        {employments.length > 0 && <div className="form-field"><label htmlFor="filter-employment">Employment type</label><select id="filter-employment" value={employment} onChange={(e) => change(setEmployment, e.target.value)}><option value="">All employment types</option>{employments.map((v) => <option key={v} value={v}>{EMPLOYMENT_LABELS[v]}</option>)}</select></div>}
        <div className="form-field"><label htmlFor="results-sort">Sort jobs</label><select id="results-sort" value={sort} onChange={(e) => change(setSort, e.target.value)}><option value="newest">Newest posting first</option><option value="oldest">Oldest posting first</option><option value="title">Title A–Z</option><option value="company">Company A–Z</option></select></div>
      </div>
      <p className="search-note" role="status">Showing {filtered.length ? offset + 1 : 0}–{Math.min(offset + pageSize, filtered.length)} of {filtered.length} matching jobs · {loaded.length} loaded</p>
      {!filtered.length ? <p className="notice">No jobs match your filters. Try changing or clearing them.</p> :
        <table className="job-results-table" role="table" aria-label="Saved job results">
          <thead role="rowgroup"><tr role="row">{['Job title', 'Company', 'Location', 'Source', 'Employment type', 'Workplace type', 'Posted date', 'Action'].map((label) => <th key={label} scope="col" role="columnheader">{label}</th>)}</tr></thead>
          <tbody role="rowgroup">{visible.map((job) => <tr key={job.id} role="row">
            <td role="cell"><span className="mobile-cell-label" aria-hidden="true">Job title</span><Link className="job-title-link" to={detailUrl(job.id)}>{job.title}</Link></td>
            <td role="cell"><span className="mobile-cell-label" aria-hidden="true">Company</span>{job.company}</td>
            <td role="cell"><span className="mobile-cell-label" aria-hidden="true">Location</span>{textOrFallback(job.location)}</td>
            <td role="cell"><span className="mobile-cell-label" aria-hidden="true">Source</span>{SOURCE_LABELS[job.source]}<ExternalJobLink url={job.job_url}>Original listing</ExternalJobLink></td>
            <td role="cell"><span className="mobile-cell-label" aria-hidden="true">Employment type</span>{job.employment_type ? EMPLOYMENT_LABELS[job.employment_type] : NOT_SPECIFIED}</td>
            <td role="cell"><span className="mobile-cell-label" aria-hidden="true">Workplace type</span>{job.workplace_type ? WORKPLACE_LABELS[job.workplace_type] : NOT_SPECIFIED}</td>
            <td role="cell"><span className="mobile-cell-label" aria-hidden="true">Posted date</span>{formatDate(postingDate(job))}</td>
            <td role="cell"><Link className="text-link" to={detailUrl(job.id)} aria-label={`View details for ${job.title}`}>View details</Link></td>
          </tr>)}</tbody>
        </table>}
      <nav className="results-pagination" aria-label="Results pagination">
        <div className="form-field"><label htmlFor="results-page-size">Jobs per page</label><select id="results-page-size" value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1) }}>{[20, 50, 100].map((size) => <option key={size} value={size}>{size}</option>)}</select></div>
        <div className="pagination-actions"><button className="button" disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)}>Previous</button><span>Page {currentPage} of {pages}</span><button className="button" disabled={currentPage === pages} onClick={() => setPage(currentPage + 1)}>Next</button></div>
      </nav>
    </>}
  </>
}
