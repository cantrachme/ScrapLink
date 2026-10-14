import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import App from '../app/App'

class Stream {
  static instances: Stream[] = []
  listeners: Record<string, () => void> = {}
  onerror: (() => void) | null = null
  close = vi.fn()
  url: string
  constructor(url: string) { this.url = url; Stream.instances.push(this) }
  addEventListener(name: string, cb: () => void) { this.listeners[name] = cb }
}
const job = { id: 'job1', title: 'Published role', company: 'Employer', source: 'ashby',
  posted_date: '2026-10-12', posted_at: null, posted_text: 'datePosted: 2026-10-12',
  description: 'A complete description\nwith multiple paragraphs.', job_url: 'https://jobs.ashbyhq.com/employer/job1',
  location: null, workplace_type: null, employment_type: null, compensation: null }
const run = { search_id: 'run1', status: 'running', saved: 0, error: null, sources: {} }
const response = (value: unknown) => Promise.resolve(new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } }))

beforeEach(() => { Stream.instances = []; vi.stubGlobal('EventSource', Stream) })

it('shows only the primary discovery action and persisted full details', async () => {
  vi.stubGlobal('fetch', vi.fn(() => response({ jobs: [job], run: null, worker_available: true })))
  render(<App />)
  expect(await screen.findByText('Published role')).toBeInTheDocument()
  expect(screen.getAllByRole('button')).toHaveLength(1)
  expect(screen.getByRole('button', { name: /Search Jobs/ })).toBeEnabled()
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  expect(screen.getAllByText('Unknown')).toHaveLength(3)
  fireEvent.click(screen.getByText('Full description'))
  expect(screen.getByText(/A complete description/)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /View original posting/ })).toHaveAttribute('href', job.job_url)
})

it('starts once, disables duplicates and refreshes on job_saved SSE', async () => {
  let saved = false
  const fetcher = vi.fn((_url: string, options?: RequestInit) => {
    if (options?.method === 'POST') return response(run)
    return response({ jobs: saved ? [job] : [], run: saved ? { ...run, saved: 1 } : null, worker_available: true })
  })
  vi.stubGlobal('fetch', fetcher)
  render(<App />)
  const button = await screen.findByRole('button', { name: /Search Jobs/ })
  await waitFor(() => expect(button).toBeEnabled())
  fireEvent.click(button)
  await waitFor(() => expect(screen.getByRole('button', { name: /Searching/ })).toBeDisabled())
  fireEvent.click(button)
  expect(fetcher.mock.calls.filter(c => c[1]?.method === 'POST')).toHaveLength(1)
  await waitFor(() => expect(Stream.instances).toHaveLength(1))
  saved = true
  act(() => Stream.instances[0].listeners.job_saved())
  expect(await screen.findByText('Published role')).toBeInTheDocument()
})

it('restores a running run on refresh and displays source errors and zero results', async () => {
  const current = { ...run, sources: { greenhouse: { source: 'greenhouse', status: 'failed', scanned: 5, saved: 0, undated: 0, error: 'HTTP 403 at source' }, lever: { source: 'lever', status: 'completed', scanned: 40, saved: 0, undated: 40, error: null } } }
  vi.stubGlobal('fetch', vi.fn(() => response({ jobs: [job], run: current, worker_available: true })))
  const view = render(<App />)
  expect(await screen.findByText('HTTP 403 at source')).toBeInTheDocument()
  expect(screen.getByText('completed · 0 saved · 40 checked')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /Searching/ })).toBeDisabled()
  view.unmount()
  expect(Stream.instances[0].close).toHaveBeenCalled()
  render(<App />)
  expect(await screen.findByText('Published role')).toBeInTheDocument()
  expect(Stream.instances.at(-1)?.url).toContain('/run1/events')
})

it('surfaces connection errors without losing saved results', async () => {
  vi.stubGlobal('fetch', vi.fn((_url: string, options?: RequestInit) => options?.method === 'POST'
    ? Promise.resolve(new Response(JSON.stringify({ detail: 'Discovery worker is not running' }), { status: 503 }))
    : response({ jobs: [job], run: null, worker_available: true })))
  render(<App />)
  await screen.findByText('Published role')
  fireEvent.click(screen.getByRole('button', { name: /Search Jobs/ }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Discovery worker is not running')
  expect(screen.getByText('Published role')).toBeInTheDocument()
})

it('does not render unsafe original links', async () => {
  vi.stubGlobal('fetch', vi.fn(() => response({ jobs: [{ ...job, job_url: 'javascript:alert(1)' }], run: null, worker_available: true })))
  render(<App />)
  await screen.findByText('Published role')
  expect(screen.queryByRole('link', { name: /View original posting/ })).not.toBeInTheDocument()
})
