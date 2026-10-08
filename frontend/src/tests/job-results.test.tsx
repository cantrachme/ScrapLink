import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SearchDetailsPage } from '../pages/SearchDetailsPage'
import { JobDetailsPage } from '../pages/JobDetailsPage'
import { completed, extracted, installEventSource, json, MockEventSource, SEARCH_ID, stream, summary, task } from './search-fixtures'
import { job, makeJob } from './job-fixtures'
import type { PersistedJob } from '../types/job'

function setup(jobs: PersistedJob[] = [job], status = 'completed') {
  vi.mocked(fetch).mockImplementation((url) => Promise.resolve(json(String(url).endsWith('/results') ? { ...summary, status, jobs } : String(url).includes('/search/') ? { ...task, status } : job)))
  return mount()
}
function mount() {
  return render(<MemoryRouter initialEntries={[`/searches/${SEARCH_ID}`]}><Routes>
    <Route path="/searches/:searchId" element={<SearchDetailsPage />} />
    <Route path="/jobs/:jobId" element={<JobDetailsPage />} />
  </Routes></MemoryRouter>)
}
const table = () => screen.getByRole('table', { name: 'Saved job results' })
const titles = () => within(table()).getAllByRole('link').filter((a) => a.classList.contains('job-title-link')).map((a) => a.textContent)
const change = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } })
beforeEach(() => { installEventSource(); vi.stubGlobal('fetch', vi.fn()) })

describe('saved search results', () => {
  it('loads saved results independently of search metadata and cancels on departure', async () => {
    vi.mocked(fetch).mockImplementation((url) => String(url).endsWith('/results') ? new Promise(() => {}) : Promise.resolve(json({ ...task, status: 'completed' })))
    const view = mount()
    expect(await screen.findByText('Loading persisted results…')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    view.unmount()
    const request = vi.mocked(fetch).mock.calls.find(([url]) => String(url).endsWith('/results'))!
    expect(request[1]?.signal?.aborted).toBe(true)
  })
  it('renders real jobs, loaded counts, all columns and safe source links', async () => {
    setup([{ ...job, location: 'London', workplace_type: 'hybrid', employment_type: 'contract', posted_date: '2026-10-07' }])
    await screen.findByRole('table')
    expect(titles()).toEqual(['Python Engineer'])
    expect(screen.getByText(/1 loaded jobs/)).toBeInTheDocument()
    expect(within(table()).getAllByRole('columnheader')).toHaveLength(8)
    expect(within(table()).getByText('London')).toBeInTheDocument()
    expect(within(table()).getByRole('link', { name: 'Original listing' })).toHaveAttribute('rel', 'noopener noreferrer')
    expect(MockEventSource.instances).toHaveLength(0)
  })
  it('deduplicates loaded jobs by stable database ID', async () => {
    setup([job, job, { ...job, id: job.id.toUpperCase() }]); await screen.findByRole('table')
    expect(titles()).toHaveLength(1)
    expect(screen.getByText(/1 loaded jobs/)).toBeInTheDocument()
  })
  it('shows a completed empty result state', async () => {
    setup([]); expect(await screen.findByText('No jobs were saved for this search.')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })
  it('shows request failure and retries without another event stream', async () => {
    vi.mocked(fetch).mockImplementation((url) => Promise.resolve(String(url).endsWith('/results') ? json({ detail: 'Unavailable' }, 503) : json({ ...task, status: 'completed' })))
    mount(); expect(await screen.findByRole('alert')).toHaveTextContent('Unavailable')
    vi.mocked(fetch).mockImplementation((url) => Promise.resolve(json(String(url).endsWith('/results') ? { ...summary, jobs: [job] } : { ...task, status: 'completed' })))
    fireEvent.click(screen.getByRole('button', { name: 'Reload results summary' }))
    await screen.findByRole('table'); expect(MockEventSource.instances).toHaveLength(0)
  })
  it('combines title and company search case-insensitively and shows no matches', async () => {
    setup([job, makeJob(2, { title: 'Python Lead', company: 'Other' }), makeJob(3, { title: 'Designer' })]); await screen.findByRole('table')
    change('Search job titles', ' PYTHON '); expect(titles()).toHaveLength(2)
    change('Search companies', 'exam'); expect(titles()).toEqual(['Python Engineer'])
    change('Search companies', 'missing'); expect(screen.getByText(/No jobs match your filters/)).toBeInTheDocument()
    expect(screen.getByText('Showing 0–0 of 0 matching jobs · 3 loaded')).toBeInTheDocument()
  })
  it('filters only explicit source, workplace and employment metadata', async () => {
    setup([job, makeJob(2, { source: 'wellfound', workplace_type: 'remote', employment_type: 'full_time' }), makeJob(3, { workplace_type: 'remote', employment_type: 'contract' })]); await screen.findByRole('table')
    change('Workplace type', 'remote'); expect(titles()).toHaveLength(2)
    change('Employment type', 'full_time'); expect(titles()).toEqual(['Role 002'])
    change('Source', 'linkedin'); expect(screen.getByText(/No jobs match/)).toBeInTheDocument()
    change('Source', 'wellfound'); expect(titles()).toEqual(['Role 002'])
  })
  it('sorts dates with posted_at priority, valid date fallback, and unknown dates last', async () => {
    setup([makeJob(1, { posted_at: '2026-10-08T05:00:00Z', posted_date: '2020-01-01' }), makeJob(2, { posted_at: 'invalid', posted_date: '2026-10-07' }), makeJob(3, { posted_at: '2026-02-30', posted_date: 'invalid' }), makeJob(4)])
    await screen.findByRole('table'); expect(titles()).toEqual(['Role 001', 'Role 002', 'Role 003', 'Role 004'])
    change('Sort jobs', 'oldest'); expect(titles()).toEqual(['Role 002', 'Role 001', 'Role 003', 'Role 004'])
  })
  it('sorts alphabetically by title and company', async () => {
    setup([makeJob(1, { title: 'Zebra', company: 'Alpha' }), makeJob(2, { title: 'Alpha', company: 'Zebra' })]); await screen.findByRole('table')
    change('Sort jobs', 'title'); expect(titles()).toEqual(['Alpha', 'Zebra'])
    change('Sort jobs', 'company'); expect(titles()).toEqual(['Zebra', 'Alpha'])
  })
  it('paginates 20/50/100, keeps sorting across pages, and resets on filter changes', async () => {
    setup(Array.from({ length: 101 }, (_, i) => makeJob(i + 1))); await screen.findByRole('table')
    expect(titles()).toHaveLength(20)
    change('Sort jobs', 'title')
    fireEvent.click(screen.getByRole('button', { name: 'Next' })); expect(titles()[0]).toBe('Role 021')
    expect(screen.getByText('Showing 21–40 of 101 matching jobs · 101 loaded')).toBeInTheDocument()
    change('Search job titles', 'Role 0'); expect(screen.getByText('Page 1 of 5')).toBeInTheDocument()
    change('Search job titles', ''); change('Jobs per page', '50'); expect(titles()).toHaveLength(50)
    fireEvent.click(screen.getByRole('button', { name: 'Next' })); expect(titles()[0]).toBe('Role 051')
    change('Jobs per page', '100'); expect(titles()).toHaveLength(100)
    fireEvent.click(screen.getByRole('button', { name: 'Next' })); expect(titles()).toEqual(['Role 101'])
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Previous' })); expect(titles()[0]).toBe('Role 001')
  })
  it('shows neutral missing metadata without inferring remote from description', async () => {
    setup([{ ...job, description: 'Remote job', job_url: 'javascript:alert(1)' }]); await screen.findByRole('table')
    expect(within(table()).getAllByText('Not specified')).toHaveLength(4)
    expect(screen.queryByLabelText('Workplace type')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Original listing' })).not.toBeInTheDocument()
  })
  it('waits for committed results and reconciles only once on repeated completion events', async () => {
    setup([job], 'running'); await screen.findByText('Running')
    act(() => stream().emit('job_extracted', extracted, 3))
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.getByText(/Live extraction events above are not saved/)).toBeInTheDocument()
    act(() => { stream().emit('search_completed', completed, 4); stream().emit('search_completed', completed, 5) })
    await screen.findByRole('table')
    expect(vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith('/results'))).toHaveLength(1)
    expect(MockEventSource.instances).toHaveLength(1)
  })
  it.each([{ jobs: [] }, { jobs: [job] }])('handles failed searches with zero or partial persisted jobs', async ({ jobs }) => {
    setup(jobs, 'failed')
    await waitFor(() => expect(screen.queryByText('Loading persisted results…')).not.toBeInTheDocument())
    expect(await screen.findByText(jobs.length ? /saved results below may be incomplete/ : /No saved jobs are available/)).toBeInTheDocument()
  })
  it('navigates by database ID with a durable search query parameter', async () => {
    setup(); const title = await screen.findByRole('link', { name: 'Python Engineer' })
    expect(title).toHaveAttribute('href', `/jobs/${job.id}?searchId=${SEARCH_ID}`)
    fireEvent.click(title)
    expect(await screen.findByRole('heading', { name: 'Python Engineer' })).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledWith(`/api/v1/jobs/${job.id}`, expect.anything())
    expect(screen.getByRole('link', { name: 'Back to search results' })).toHaveAttribute('href', `/searches/${SEARCH_ID}`)
  })
  it('provides labelled cells for the responsive card layout without duplicate rows', async () => {
    setup(); await screen.findByRole('table')
    const rows = within(table()).getAllByRole('row')
    expect(rows).toHaveLength(2)
    expect(rows[1].querySelectorAll('.mobile-cell-label')).toHaveLength(7)
    expect(within(rows[1]).getByRole('link', { name: /View details/ })).toBeInTheDocument()
  })
})
