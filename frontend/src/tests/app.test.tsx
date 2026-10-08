import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../app/App'
import { AppRoutes } from '../app/router'

const healthy = {
  status: 'healthy',
  service: 'ScrapLink API',
  environment: 'development',
  version: '0.1.0',
}

function renderRoute(path = '/') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockImplementation(() =>
        Promise.resolve(new Response(JSON.stringify(healthy))),
      ),
  )
})

describe('application foundation', () => {
  it('renders the real application and connects through the relative health path', async () => {
    window.history.replaceState({}, '', '/')
    render(<App />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Welcome to ScrapLink.',
    )
    expect(
      screen.getByRole('link', { name: 'ScrapLink dashboard' }),
    ).toBeInTheDocument()
    expect(await screen.findByText('Connected')).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledWith(
      '/health',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    )
  })

  it('navigates between Job Search and Dashboard without a document navigation', async () => {
    renderRoute()
    await screen.findByText('Connected')
    const nav = screen.getByRole('navigation', { name: 'Main navigation' })
    fireEvent.click(within(nav).getByRole('link', { name: 'Job Search' }))
    expect(
      screen.getByRole('heading', { name: 'Job Search' }),
    ).toBeInTheDocument()
    expect(
      within(nav).getByRole('link', { name: 'Job Search' }),
    ).toHaveAttribute('aria-current', 'page')
    expect(
      screen.getByRole('heading', { name: 'LinkedIn' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: 'Wellfound' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('main')).toHaveFocus()
    expect(screen.getByLabelText(/Job title \/ keyword/)).toBeInTheDocument()
    fireEvent.click(within(nav).getByRole('link', { name: 'Dashboard' }))
    expect(await screen.findByText('Connected')).toBeInTheDocument()
    expect(
      within(nav).getByRole('link', { name: 'Dashboard' }),
    ).toHaveAttribute('aria-current', 'page')
  })

  it('links the dashboard call to action to Job Search', async () => {
    renderRoute()
    await screen.findByText('Connected')
    fireEvent.click(screen.getByRole('link', { name: 'Explore Job Search' }))
    expect(
      screen.getByRole('heading', { name: 'Job Search' }),
    ).toBeInTheDocument()
  })

  it('handles an unknown route and offers a route home', async () => {
    renderRoute('/missing')
    expect(
      screen.getByRole('heading', { name: 'Page not found' }),
    ).toBeInTheDocument()
    expect(fetch).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('link', { name: 'Back to Dashboard' }))
    expect(await screen.findByText('Connected')).toBeInTheDocument()
  })

  it.each([
    ['/searches/search-123', 'Search Details', 'search-123'],
    ['/jobs/job-456', 'Job Details', 'job-456'],
  ])('reserves %s without fetching or inventing results', (path, title, id) => {
    renderRoute(path)
    expect(screen.getByRole('heading', { name: title })).toBeInTheDocument()
    expect(screen.getByText(id)).toBeInTheDocument()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('provides navigation labels, a skip link, and an accessible collapse toggle', () => {
    renderRoute('/search')
    expect(
      screen.getByRole('navigation', { name: 'Main navigation' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: 'Skip to content' }),
    ).toHaveAttribute('href', '#main-content')
    fireEvent.click(screen.getByRole('button', { name: 'Collapse sidebar' }))
    expect(
      screen.getByRole('button', { name: 'Expand sidebar' }),
    ).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByRole('link', { name: 'Dashboard' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Open navigation' }))
    expect(
      screen.getByRole('button', { name: 'Close navigation' }),
    ).toHaveAttribute('aria-expanded', 'true')
    fireEvent.keyDown(
      screen.getByRole('button', { name: 'Close navigation' }),
      { key: 'Escape' },
    )
    expect(
      screen.getByRole('button', { name: 'Open navigation' }),
    ).toHaveFocus()
  })
})

describe('backend connectivity', () => {
  it('shows loading while the health request is pending', () => {
    vi.mocked(fetch).mockReturnValue(new Promise(() => {}))
    renderRoute()
    expect(screen.getByRole('status')).toHaveTextContent('Loading')
    expect(
      screen.getByRole('button', { name: /Check connection/ }),
    ).toBeDisabled()
  })

  it.each([
    ['network failure', () => Promise.reject(new TypeError('Failed to fetch'))],
    [
      'HTTP failure',
      () => Promise.resolve(new Response('Unavailable', { status: 503 })),
    ],
    [
      'invalid JSON',
      () => Promise.resolve(new Response('<html>Proxy error</html>')),
    ],
  ])(
    'shows unavailable after %s and keeps navigation usable',
    async (_label, response) => {
      vi.mocked(fetch).mockImplementation(response)
      renderRoute()
      expect(await screen.findByText('Unavailable')).toBeInTheDocument()
      expect(screen.getByText(/Start FastAPI on port 8000/)).toBeInTheDocument()
      fireEvent.click(screen.getByRole('link', { name: 'Job Search' }))
      expect(
        screen.getByRole('heading', { name: 'Job Search' }),
      ).toBeInTheDocument()
    },
  )

  it('retries a failed connection successfully', async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new TypeError('Offline'))
    renderRoute()
    await screen.findByText('Unavailable')
    fireEvent.click(screen.getByRole('button', { name: /Check connection/ }))
    expect(await screen.findByText('Connected')).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('aborts an unfinished request when leaving the dashboard', () => {
    vi.mocked(fetch).mockReturnValue(new Promise(() => {}))
    const view = renderRoute()
    const options = vi.mocked(fetch).mock.calls[0][1]
    view.unmount()
    expect(options?.signal?.aborted).toBe(true)
  })

  it('times out a stalled health request', async () => {
    vi.useFakeTimers()
    try {
      vi.mocked(fetch).mockReturnValue(new Promise(() => {}))
      renderRoute()
      await act(() => vi.advanceTimersByTimeAsync(8000))
      expect(screen.getByRole('status')).toHaveTextContent('Unavailable')
      expect(vi.mocked(fetch).mock.calls[0][1]?.signal?.aborted).toBe(true)
    } finally {
      vi.useRealTimers()
    }
  })
})
