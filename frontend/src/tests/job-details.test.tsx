import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { JobDetailsPage } from '../pages/JobDetailsPage'
import { job, JOB_ID } from './job-fixtures'
import { json, SEARCH_ID } from './search-fixtures'

function setup(path = `/jobs/${JOB_ID}`) {
  return render(<MemoryRouter initialEntries={[path]}><Routes><Route path="/jobs/:jobId?" element={<JobDetailsPage />} /><Route path="/searches/:searchId" element={<p>Returned to results</p>} /></Routes></MemoryRouter>)
}
beforeEach(() => vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(json(job)))))

describe('complete stored job details', () => {
  it('shows loading and aborts the request when leaving', () => {
    vi.mocked(fetch).mockReturnValue(new Promise(() => {}))
    const view = setup()
    expect(screen.getByRole('status')).toHaveTextContent('Loading job details')
    view.unmount(); expect(vi.mocked(fetch).mock.calls[0][1]?.signal?.aborted).toBe(true)
  })
  it('fetches a job on direct navigation without cached navigation state', async () => {
    setup(); expect(await screen.findByRole('heading', { name: 'Python Engineer' })).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledWith(`/api/v1/jobs/${JOB_ID}`, expect.anything())
    expect(screen.getByText('Example', { selector: '.job-company' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to Job Search' })).toHaveAttribute('href', '/search')
  })
  it.each(['/jobs/invalid', '/jobs'])('rejects invalid or missing UUID at %s', (path) => {
    setup(path); expect(screen.getByRole('alert')).toHaveTextContent('Invalid job ID')
    expect(fetch).not.toHaveBeenCalled()
  })
  it.each([[404, 'Job not found'], [422, 'backend rejected this job ID'], [503, 'Database unavailable']])('handles HTTP %s', async (status, message) => {
    vi.mocked(fetch).mockResolvedValue(json({ detail: 'Database unavailable' }, Number(status)))
    setup(); expect(await screen.findByRole('alert')).toHaveTextContent(String(message))
  })
  it('handles an unavailable backend and supports retry', async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new TypeError('offline'))
    setup(); expect(await screen.findByRole('alert')).toHaveTextContent('Unable to reach the backend')
    fireEvent.click(screen.getByRole('button', { name: 'Reload job' }))
    expect(await screen.findByRole('heading', { name: 'Python Engineer' })).toBeInTheDocument()
  })
  it('preserves the entire plain text description including paragraphs and final text', async () => {
    const description = 'First paragraph.\n\n' + 'Long description line.\n'.repeat(2000) + 'Final paragraph.'
    vi.mocked(fetch).mockResolvedValue(json({ ...job, description }))
    const view = setup(); await screen.findByRole('heading', { name: 'Python Engineer' })
    expect(view.container.querySelector('.job-description')?.textContent).toBe(description)
  })
  it('converts HTML paragraphs and breaks to text without rendering source HTML or XSS', async () => {
    vi.mocked(fetch).mockResolvedValue(json({ ...job, description: '<p>First &amp; second</p><p>Next<br>line</p><script>alert(1)</script><img src=x onerror="alert(2)"><iframe src="https://evil.example"></iframe><style>body{display:none}</style><a href="javascript:alert(3)">Readable link text</a>' }))
    const view = setup(); await screen.findByRole('heading', { name: 'Python Engineer' })
    const description = view.container.querySelector('.job-description')!
    expect(description.textContent).toContain('First & second\n\nNext\nline')
    expect(description.textContent).toContain('Readable link text')
    expect(description.textContent).not.toContain('alert(')
    expect(description.querySelector('script, img, iframe, style, a')).toBeNull()
  })
  it('renders available metadata, lists, experience, timestamps and source links', async () => {
    vi.mocked(fetch).mockResolvedValue(json({ ...job, location: 'London', workplace_type: 'hybrid', employment_type: 'contract', seniority_level: 'Senior', status: 'active', responsibilities: ['Build services'], requirements: ['API experience'], skills: ['Python'], experience_min_years: 0, experience_max_years: 5, posted_date: '2026-10-07', last_verified_at: '2026-10-08T05:00:00Z', application_url: 'https://example.com/apply', company_url: 'https://example.com' }))
    setup(); await screen.findByRole('heading', { name: 'Python Engineer' })
    for (const value of ['London', 'Hybrid', 'Contract', 'Senior', 'Active', 'Build services', 'API experience', 'Python', '0 years', '5 years', '123']) expect(screen.getByText(value)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open application link' })).toHaveAttribute('href', 'https://example.com/apply')
    expect(screen.getByRole('link', { name: 'https://example.com' })).toHaveAttribute('rel', 'noopener noreferrer')
  })
  it.each([
    [{ raw_text: null, currency: 'INR', min_amount: 500, max_amount: 800, period: 'hour' }, 'INR 500–800 per hour'],
    [{ raw_text: null, currency: null, min_amount: 0, max_amount: 800, period: null }, '0–800'],
    [{ raw_text: null, currency: 'EUR', min_amount: null, max_amount: 5000, period: 'month' }, 'EUR Up to 5,000 per month'],
    [{ raw_text: 'Competitive, equity included', currency: null, min_amount: null, max_amount: null, period: null }, 'Competitive, equity included'],
  ])('uses actual compensation without currency or annual assumptions', async (compensation, expected) => {
    vi.mocked(fetch).mockResolvedValue(json({ ...job, compensation }))
    setup(); expect(await screen.findByText(expected)).toBeInTheDocument()
    expect(screen.queryByText(/USD|per year/)).not.toBeInTheDocument()
  })
  it('handles missing optional values and hides empty sections', async () => {
    setup(); await screen.findByRole('heading', { name: 'Python Engineer' })
    expect(screen.getByText('No description was provided for this job.')).toBeInTheDocument()
    for (const heading of ['Responsibilities', 'Requirements', 'Skills', 'Experience', 'Compensation']) expect(screen.queryByRole('heading', { name: heading })).not.toBeInTheDocument()
    expect(screen.getAllByText('Not specified').length).toBeGreaterThan(0)
    expect(screen.queryByRole('link', { name: 'Open application link' })).not.toBeInTheDocument()
  })
  it.each(['javascript:alert(1)', 'data:text/html,evil', '//evil.example/path', 'https://user:password@example.com', 'not a url'])('never links unsafe source URLs: %s', async (url) => {
    vi.mocked(fetch).mockResolvedValue(json({ ...job, job_url: url, company_url: url, application_url: url }))
    const view = setup(); await screen.findByRole('heading', { name: 'Python Engineer' })
    expect(screen.queryByRole('link', { name: 'Open original listing' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Open application link' })).not.toBeInTheDocument()
    expect(view.container.querySelectorAll('a[target="_blank"]')).toHaveLength(0)
  })
  it('restores back navigation from the URL after direct entry', async () => {
    setup(`/jobs/${JOB_ID}?searchId=${SEARCH_ID}`); await screen.findByRole('heading', { name: 'Python Engineer' })
    fireEvent.click(screen.getByRole('link', { name: 'Back to search results' }))
    expect(screen.getByText('Returned to results')).toBeInTheDocument()
  })
  it('ignores an invalid search ID in the query string', async () => {
    setup(`/jobs/${JOB_ID}?searchId=../../bad`); await screen.findByRole('heading', { name: 'Python Engineer' })
    expect(screen.getByRole('link', { name: 'Back to Job Search' })).toHaveAttribute('href', '/search')
  })
  it('rejects a response for a different job', async () => {
    vi.mocked(fetch).mockResolvedValue(json({ ...job, id: SEARCH_ID }))
    setup(); expect(await screen.findByRole('alert')).toHaveTextContent('malformed job fields')
  })
})
