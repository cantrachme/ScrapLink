import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SearchDetailsPage } from '../pages/SearchDetailsPage'
import { completed, extracted, failure, installEventSource, json, MockEventSource, page, SEARCH_ID, started, stream, summary, task } from './search-fixtures'

function setup(path = `/searches/${SEARCH_ID}`) {
  return render(<MemoryRouter initialEntries={[path]}><Routes>
    <Route path="/searches/:searchId?" element={<SearchDetailsPage />} />
  </Routes></MemoryRouter>)
}
const metric = (label: string) => screen.getByText(label, { selector: 'dt' }).parentElement!
beforeEach(() => {
  installEventSource()
  vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => Promise.resolve(json(url.endsWith('/results') ? summary : task))))
})

describe('persisted search progress page', () => {
  it('shows loading and aborts the initial request on unmount', () => {
    vi.mocked(fetch).mockReturnValue(new Promise(() => {}))
    const view = setup()
    expect(screen.getByRole('status')).toHaveTextContent('Loading search')
    expect(MockEventSource.instances).toHaveLength(0)
    view.unmount()
    expect(vi.mocked(fetch).mock.calls[0][1]?.signal?.aborted).toBe(true)
  })
  it.each(['/searches/not-a-uuid', '/searches'])('rejects invalid or missing ID at %s', (path) => {
    setup(path)
    expect(screen.getByRole('alert')).toHaveTextContent('Invalid search ID')
    expect(fetch).not.toHaveBeenCalled()
    expect(MockEventSource.instances).toHaveLength(0)
  })
  it('loads an existing queued search by direct navigation without POSTing', async () => {
    setup()
    expect(await screen.findByText('Queued')).toBeInTheDocument()
    expect(screen.getByText(/Waiting for a worker/)).toBeInTheDocument()
    expect(screen.getByText(SEARCH_ID)).toBeInTheDocument()
    expect(screen.getByText('United States')).toBeInTheDocument()
    expect(screen.getByText('Past 24 hours')).toBeInTheDocument()
    expect(within(metric('Unique jobs discovered')).getByText('0')).toBeInTheDocument()
    expect(screen.getByText('No progress events received yet.')).toBeInTheDocument()
    act(() => stream().open())
    expect(screen.getByText('Queued')).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(vi.mocked(fetch).mock.calls[0][1]?.method).toBeUndefined()
  })
  it('renders persisted running state before any events arrive', async () => {
    vi.mocked(fetch).mockResolvedValue(json({ ...task, status: 'running' }))
    setup()
    expect(await screen.findByText('Running')).toBeInTheDocument()
    expect(screen.getByText('The search is running. Waiting for collection progress.')).toBeInTheDocument()
  })
  it('shows events, partial extraction failures, completion and persisted summary', async () => {
    setup(); await screen.findByText('Queued')
    act(() => {
      stream().open()
      stream().emit('search_started', started, 2)
      stream().emit('page_discovered', page, 3)
      stream().emit('job_extracted', extracted, 4)
      stream().emit('job_failed', failure, 5)
    })
    expect(screen.getByText('Running')).toBeInTheDocument()
    expect(screen.getByText('Listing page 1 processed — 18 new jobs discovered')).toBeInTheDocument()
    expect(screen.getByText('Job extracted — Engineer · Example')).toBeInTheDocument()
    expect(screen.getByText(/Job extraction failed — Job description unavailable/)).toBeInTheDocument()
    expect(within(metric('Failed extractions')).getByText('1')).toBeInTheDocument()
    expect(screen.getByText(/Date-filter exclusions are not failures/)).toBeInTheDocument()
    vi.mocked(fetch).mockImplementation((url) => Promise.resolve(json(String(url).endsWith('/results') ? summary : { ...task, status: 'completed', updated_at: '2026-10-08T06:00:00Z' })))
    act(() => stream().emit('search_completed', completed, 6))
    expect(await screen.findByText(/2 qualifying jobs saved/)).toBeInTheDocument()
    expect(screen.getByText('Completed')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'View persisted results summary' })).toHaveAttribute('href', '#search-results')
    expect(stream().close).toHaveBeenCalledTimes(1)
    expect(screen.getByText(/Step 49/)).toBeInTheDocument()
  })
  it('shows transient connection loss without treating a queued job as failed', async () => {
    setup(); await screen.findByText('Queued')
    await act(async () => stream().disconnect())
    expect(screen.getByText('Reconnecting to live progress…')).toBeInTheDocument()
    expect(screen.getByText('Queued')).toBeInTheDocument()
    act(() => stream().open())
    expect(screen.getByText('Live progress connected')).toBeInTheDocument()
    expect(MockEventSource.instances).toHaveLength(1)
  })
  it('reconstructs progress by replaying from the beginning after a page remount', async () => {
    const first = setup(); await screen.findByText('Queued')
    act(() => { stream().emit('page_discovered', page, 3); stream().emit('job_extracted', extracted, 4) })
    const old = stream()
    first.unmount()
    setup(); await screen.findByText('Queued')
    expect(old.close).toHaveBeenCalled()
    expect(stream().url).toBe(`/api/v1/jobs/search/${SEARCH_ID}/events`)
    act(() => { stream().emit('page_discovered', page, 3); stream().emit('job_extracted', extracted, 4); stream().emit('job_extracted', extracted, 4) })
    expect(within(metric('Qualifying jobs extracted')).getByText('1')).toBeInTheDocument()
    expect(screen.getAllByText('Job extracted — Engineer · Example')).toHaveLength(1)
  })
  it('loads terminal zero results after refresh without opening EventSource', async () => {
    vi.mocked(fetch).mockImplementation((url) => Promise.resolve(json(String(url).endsWith('/results') ? { ...summary, total_discovered: 0, total_extracted: 0, total_failed: 0 } : { ...task, status: 'completed' })))
    setup()
    expect(await screen.findByText(/Search completed with zero qualifying jobs/)).toBeInTheDocument()
    expect(screen.getByText(/historical activity and page counts are unavailable/)).toBeInTheDocument()
    expect(within(metric('Pages processed')).getByText('—')).toBeInTheDocument()
    expect(MockEventSource.instances).toHaveLength(0)
  })
  it('displays a permanent persisted backend failure', async () => {
    vi.mocked(fetch).mockImplementation((url) => Promise.resolve(json(String(url).endsWith('/results') ? { ...summary, status: 'failed', total_extracted: 0 } : { ...task, status: 'failed', error: 'RuntimeError: Browser unavailable' })))
    setup()
    expect(await screen.findByRole('alert')).toHaveTextContent('RuntimeError: Browser unavailable')
    await screen.findByText(/0 qualifying jobs saved/)
    expect(within(metric('Qualifying jobs extracted')).getByText('—')).toBeInTheDocument()
    expect(MockEventSource.instances).toHaveLength(0)
    expect(screen.queryByRole('button', { name: /Retry Search|Cancel|Pause|Resume/ })).not.toBeInTheDocument()
  })
  it('displays a live search_failed event and closes the connection', async () => {
    setup(); await screen.findByText('Queued')
    act(() => stream().emit('search_failed', { search_id: SEARCH_ID, status: 'failed', error: 'Search execution failed' }, 2))
    expect(await screen.findByRole('alert')).toHaveTextContent('Search execution failed')
    await screen.findByText(/qualifying jobs saved/)
    expect(stream().close).toHaveBeenCalledTimes(1)
  })
  it.each([
    ['not found', () => Promise.resolve(json({ detail: 'Search task not found' }, 404)), 'Search not found.'],
    ['offline', () => Promise.reject(new TypeError('offline')), 'Unable to reach the backend'],
    ['malformed', () => Promise.resolve(json({ ...task, status: 'invented' })), 'malformed search fields'],
  ])('handles %s without opening a stream', async (_name, response, text) => {
    vi.mocked(fetch).mockImplementation(response)
    setup()
    expect(await screen.findByRole('alert')).toHaveTextContent(text)
    expect(MockEventSource.instances).toHaveLength(0)
  })
  it('can reload a failed retrieval without creating a task', async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new TypeError('offline'))
    setup(); await screen.findByRole('alert')
    fireEvent.click(screen.getByRole('button', { name: 'Reload search' }))
    expect(await screen.findByText('Queued')).toBeInTheDocument()
    expect(vi.mocked(fetch).mock.calls.every(([, options]) => options?.method === undefined)).toBe(true)
  })
  it('retains completion if the results request fails and allows summary reload', async () => {
    vi.mocked(fetch).mockImplementation((url) => Promise.resolve(String(url).endsWith('/results') ? json({ detail: 'Database unavailable' }, 500) : json({ ...task, status: 'completed' })))
    setup()
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load persisted results')
    expect(screen.getByText('Completed')).toBeInTheDocument()
    vi.mocked(fetch).mockImplementation((url) => Promise.resolve(json(String(url).endsWith('/results') ? summary : { ...task, status: 'completed' })))
    fireEvent.click(screen.getByRole('button', { name: 'Reload results summary' }))
    await waitFor(() => expect(screen.getByText(/2 qualifying jobs saved/)).toBeInTheDocument())
    expect(MockEventSource.instances).toHaveLength(0)
  })
})
