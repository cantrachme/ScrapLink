import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useParams } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SearchPage } from '../pages/SearchPage'
import { json, SEARCH_ID } from './search-fixtures'

function Destination() { return <p>Search destination: {useParams().searchId}</p> }
function setup() {
  render(<MemoryRouter initialEntries={['/search']}><Routes>
    <Route path="/search" element={<SearchPage />} />
    <Route path="/searches/:searchId" element={<Destination />} />
  </Routes></MemoryRouter>)
}
const change = (label: string | RegExp, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } })
const submit = () => fireEvent.click(screen.getByRole('button', { name: 'Start Search' }))
beforeEach(() => vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(json({ search_id: SEARCH_ID, status: 'pending', message: 'Queued' }, 202)))))

describe('search creation', () => {
  it('renders accessible controlled inputs and backend-compatible defaults', () => {
    setup()
    expect(screen.getByLabelText('Job source')).toHaveValue('careerhub')
    expect(screen.getByLabelText(/Job title/)).toBeRequired()
    expect(screen.getByPlaceholderText('Senior Software Engineer')).toHaveValue('')
    expect(screen.getByLabelText('Location')).toHaveValue('')
    expect(screen.getByLabelText('Posting date')).toHaveValue('any')
    expect(screen.getByLabelText('Maximum results')).toHaveValue(20)
    for (const label of ['Any time', 'Past 24 hours', 'Past 7 days', 'Past 30 days']) expect(screen.getByRole('option', { name: label })).toBeInTheDocument()
    expect(screen.getByText(/worker opens Chrome/)).toBeInTheDocument()
  })
  it.each(['', '   '])('rejects blank keyword %j without a request', (keyword) => {
    setup(); change(/Job title/, keyword); submit()
    expect(screen.getByText('Enter a job title or keyword.')).toBeInTheDocument()
    expect(screen.getByLabelText(/Job title/)).toHaveAttribute('aria-invalid', 'true')
    expect(fetch).not.toHaveBeenCalled()
  })
  it.each(['0', '-2', '501', '2.5', ''])('rejects invalid maximum %j', (value) => {
    setup(); change(/Job title/, 'Engineer'); change('Maximum results', value); submit()
    expect(screen.getByText('Enter a whole number from 1 to 500.')).toBeInTheDocument()
    expect(fetch).not.toHaveBeenCalled()
  })
  it.each(['1', '500'])('accepts the backend limit boundary %s', async (value) => {
    setup(); change(/Job title/, 'Engineer'); change('Maximum results', value); submit()
    await screen.findByText(`Search destination: ${SEARCH_ID}`)
    expect(JSON.parse(String(vi.mocked(fetch).mock.calls[0][1]?.body)).max_results).toBe(Number(value))
  })
  it('rejects overlong keyword and location inline', () => {
    setup(); change(/Job title/, 'a'.repeat(201)); change('Location', 'b'.repeat(201)); submit()
    expect(screen.getAllByText('Use 200 characters or fewer.')).toHaveLength(2)
    expect(fetch).not.toHaveBeenCalled()
  })
  it('POSTs trimmed inputs as JSON and navigates using the queued response ID', async () => {
    setup(); change(/Job title/, '  Senior Software Engineer  '); change('Location', '  New York  ')
    change('Posting date', '7d'); change('Maximum results', '30'); submit()
    await screen.findByText(`Search destination: ${SEARCH_ID}`)
    const [url, options] = vi.mocked(fetch).mock.calls[0]
    expect(url).toBe('/api/v1/jobs/search')
    expect(options?.method).toBe('POST')
    expect(new Headers(options?.headers).get('Content-Type')).toBe('application/json')
    expect(JSON.parse(String(options?.body))).toEqual({ source: 'careerhub', keyword: 'Senior Software Engineer', location: 'New York', date_posted: '7d', max_results: 30, watch_mode: true, watch_delay_seconds: 2 })
  })
  it('prevents duplicate requests while pending and shows loading', async () => {
    let resolve!: (value: Response) => void
    vi.mocked(fetch).mockReturnValue(new Promise((done) => { resolve = done }))
    setup(); change(/Job title/, 'Engineer'); submit()
    const button = screen.getByRole('button', { name: 'Creating search…' })
    expect(button).toBeDisabled()
    fireEvent.click(button)
    fireEvent.submit(button.closest('form')!)
    expect(fetch).toHaveBeenCalledTimes(1)
    await act(async () => resolve(json({ search_id: SEARCH_ID, status: 'pending', message: 'Queued' }, 202)))
    expect(screen.getByText(`Search destination: ${SEARCH_ID}`)).toBeInTheDocument()
  })
  it.each([400, 422])('shows backend validation at HTTP %s and preserves entries', async (status) => {
    vi.mocked(fetch).mockResolvedValue(json({ detail: [{ loc: ['body', 'keyword'], msg: 'Unsupported keyword' }] }, status))
    setup(); change(/Job title/, 'My role'); submit()
    expect(await screen.findByRole('alert')).toHaveTextContent('keyword: Unsupported keyword')
    expect(screen.getByLabelText(/Job title/)).toHaveValue('My role')
    expect(screen.getByRole('button', { name: 'Start Search' })).toBeEnabled()
  })
  it.each([
    ['network', () => Promise.reject(new TypeError('offline')), 'Unable to reach the backend'],
    ['server', () => Promise.resolve(new Response('Server error', { status: 500 })), 'HTTP 500'],
    ['invalid JSON', () => Promise.resolve(new Response('not json')), 'invalid JSON'],
    ['missing fields', () => Promise.resolve(json({ search_id: SEARCH_ID })), 'malformed search fields'],
    ['invalid ID', () => Promise.resolve(json({ search_id: 'bad', status: 'pending', message: 'ok' })), 'malformed search fields'],
  ])('handles %s failures without losing input', async (_name, response, message) => {
    vi.mocked(fetch).mockImplementation(response)
    setup(); change(/Job title/, 'Engineer'); submit()
    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(screen.getByLabelText(/Job title/)).toHaveValue('Engineer')
  })
  it('times out a stalled request and does not silently retry creation', async () => {
    vi.useFakeTimers()
    try {
      vi.mocked(fetch).mockImplementation((_url, options) => new Promise((_resolve, reject) => {
        options?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
      }))
      setup(); change(/Job title/, 'Engineer'); submit()
      await act(() => vi.advanceTimersByTimeAsync(15000))
      expect(screen.getByRole('alert')).toHaveTextContent('request timed out')
      expect(screen.getByRole('alert')).toHaveTextContent('may still have accepted')
      expect(fetch).toHaveBeenCalledTimes(1)
      expect(screen.getByRole('button', { name: 'Start Search' })).toBeEnabled()
    } finally { vi.useRealTimers() }
  })
  it('accepts arbitrary Wellfound roles and locations for assisted search', async () => {
    setup(); change('Job source', 'wellfound'); change(/Job title/, 'DevOps Engineer'); change('Location', 'London'); submit()
    await screen.findByText(`Search destination: ${SEARCH_ID}`)
    expect(JSON.parse(String(vi.mocked(fetch).mock.calls[0][1]?.body))).toMatchObject({ keyword: 'DevOps Engineer', location: 'London' })
  })
  it.each(['United States', 'New York', ''])('accepts supported Wellfound location %j', async (location) => {
    setup(); change('Job source', 'wellfound'); change(/Job title/, ' Python Developer '); change('Location', location); change('Posting date', 'any'); submit()
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))
    expect(JSON.parse(String(vi.mocked(fetch).mock.calls[0][1]?.body))).toMatchObject({ source: 'wellfound', keyword: 'Python Developer', location, date_posted: 'any' })
    await screen.findByText(`Search destination: ${SEARCH_ID}`)
  })
})
