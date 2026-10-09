import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, expect, it, vi } from 'vitest'
import { AppRoutes } from '../app/router'
import { ACTIVE_OPTIONS_KEY } from '../lib/active-options'
import { isSearchTask } from '../lib/search-contract'
import { parseSearchEvent } from '../lib/search-events'
import { installEventSource, json, SEARCH_ID, stream, task } from './search-fixtures'
import { job, makeJob } from './job-fixtures'

const activeTask = { ...task, status: 'running', request: { ...task.request, mode: 'active_jobs', keyword: '', location: '' } }
const empty = { search_id: SEARCH_ID, source: null, status: 'running', source_statuses: {}, jobs: [], failures: [], discovered_urls: [], total_discovered: 0, total_extracted: 0, total_failed: 0 }
function show(path: string) { render(<MemoryRouter initialEntries={[path]}><AppRoutes /></MemoryRouter>) }
beforeEach(() => { localStorage.clear(); installEventSource() })

it('starts combined discovery from sidebar with no title or location and keeps configurable limits', async () => {
  localStorage.setItem(ACTIVE_OPTIONS_KEY, JSON.stringify({ max_results: 7, watch_mode: true, watch_delay_seconds: 2.5 }))
  vi.stubGlobal('fetch', vi.fn().mockImplementation((path: string) => Promise.resolve(json(
    path === '/api/v1/jobs/active' ? { search_id: SEARCH_ID } : path.endsWith('/results') ? empty : path === '/health' ? {} : activeTask,
  ))))
  show('/')
  expect(screen.getAllByRole('button', { name: 'Active Jobs' })).toHaveLength(2)
  fireEvent.click(within(screen.getByRole('navigation', { name: 'Main navigation' })).getByRole('button', { name: 'Active Jobs' }))
  await screen.findByRole('heading', { name: 'Active Jobs' })
  expect(fetch).toHaveBeenCalledWith('/api/v1/jobs/active', expect.objectContaining({
    method: 'POST', body: JSON.stringify({ max_results: 7, watch_mode: true, watch_delay_seconds: 2.5 }),
  }))
  expect(await screen.findByText('No jobs saved yet. No demonstration jobs are shown.')).toBeInTheDocument()
  expect(screen.queryByLabelText('Job title or keywords')).not.toBeInTheDocument()
})

it('shows saved jobs before completion, sorts both sources, and retains results after a source error', async () => {
  let rows: typeof job[] = []
  vi.stubGlobal('fetch', vi.fn().mockImplementation((path: string) => Promise.resolve(json(path.endsWith('/results') ? { ...empty, jobs: rows, total_extracted: rows.length } : activeTask))))
  show(`/active-jobs/${SEARCH_ID}`)
  await screen.findByText('No jobs saved yet. No demonstration jobs are shown.')
  rows = [{ ...job, title: 'LinkedIn role', posted_at: '2026-10-09T08:00:00Z' }]
  act(() => stream().emit('job_saved', { job_id: job.id, source: 'linkedin', total_extracted: 1 }, 1))
  expect(await screen.findByRole('link', { name: 'LinkedIn role' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Discovery · running' })).toBeInTheDocument()
  const second = makeJob(2, { source: 'wellfound', title: 'Wellfound role', posted_at: '2026-10-09T09:00:00Z' })
  rows = [...rows, second]
  act(() => stream().emit('job_saved', { job_id: second.id, source: 'wellfound', total_extracted: 2 }, 2))
  await screen.findByRole('link', { name: 'Wellfound role' })
  expect(screen.getAllByRole('row')[1]).toHaveTextContent('Wellfound role')
  act(() => stream().emit('source_status', { source: 'linkedin', status: 'access_blocked' }, 3))
  await screen.findByText(/Login, CAPTCHA, or a platform restriction stopped collection/)
  expect(screen.getByRole('link', { name: 'LinkedIn role' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Wellfound role' })).toHaveAttribute('href', expect.stringContaining('active=1'))
  expect(stream().close).not.toHaveBeenCalled()
})

it('reloads saved jobs and source limitations on reopening a completed discovery', async () => {
  vi.stubGlobal('fetch', vi.fn().mockImplementation((path: string) => Promise.resolve(json(path.endsWith('/results') ? {
    ...empty, status: 'completed', jobs: [job], source_statuses: { wellfound: 'authorization_required' },
  } : { ...activeTask, status: 'completed' }))))
  show(`/active-jobs/${SEARCH_ID}`)
  expect(await screen.findByRole('link', { name: job.title })).toBeInTheDocument()
  expect(screen.getByText(/Automated discovery is not authorized. Chrome is open/)).toBeInTheDocument()
})

it('saves permitted complete details from either source and refreshes results', async () => {
  vi.stubGlobal('fetch', vi.fn().mockImplementation((path: string) => Promise.resolve(json(path.endsWith('/results') ? empty : activeTask))))
  show(`/active-jobs/${SEARCH_ID}`)
  await screen.findByLabelText('Listing source')
  fireEvent.change(screen.getByLabelText('Listing source'), { target: { value: 'wellfound' } })
  fireEvent.change(screen.getByLabelText('Job title to save'), { target: { value: 'Designer' } })
  fireEvent.change(screen.getByLabelText('Original job URL'), { target: { value: 'https://wellfound.com/jobs/123-designer' } })
  fireEvent.change(screen.getByLabelText('Company (optional)'), { target: { value: 'Company' } })
  fireEvent.change(screen.getByLabelText('Salary as published (optional)'), { target: { value: '$90,000' } })
  fireEvent.change(screen.getByLabelText('Description (optional)'), { target: { value: 'Full description.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save job' }))
  await waitFor(() => expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/assisted-jobs'), expect.objectContaining({ body: expect.stringContaining('"source":"wellfound"') })))
  expect(await screen.findByText('Job saved. It is available in your results below.')).toBeInTheDocument()
})

it('accepts only active queryless task contracts and validates saved-job events', () => {
  expect(isSearchTask(activeTask)).toBe(true)
  expect(isSearchTask({ ...activeTask, request: { ...activeTask.request, mode: 'search' } })).toBe(false)
  const message = (data: unknown) => new MessageEvent('job_saved', { data: JSON.stringify(data), lastEventId: '3' })
  expect(parseSearchEvent('job_saved', message({ job_id: job.id, source: 'linkedin', total_extracted: 1 }), SEARCH_ID)).not.toBeNull()
  expect(parseSearchEvent('job_saved', message({ job_id: 'fake', source: 'linkedin', total_extracted: 1 }), SEARCH_ID)).toBeNull()
})
