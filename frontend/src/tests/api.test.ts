import { beforeEach, describe, expect, it, vi } from 'vitest'
import { API_PATHS, ApiError, checkHealth, requestJson } from '../lib/api'

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn())
})

describe('JSON API client', () => {
  it('returns typed health JSON from the actual endpoint', async () => {
    const health = {
      status: 'healthy',
      service: 'ScrapLink API',
      environment: 'development',
      version: '0.1.0',
    }
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify(health)))
    expect(await checkHealth()).toEqual(health)
    const [path, options] = vi.mocked(fetch).mock.calls[0]
    expect(path).toBe('/health')
    expect(new Headers(options?.headers).get('Accept')).toBe('application/json')
  })

  it.each([404, 422, 500, 503])(
    'reports HTTP %s even when the body is not JSON',
    async (status) => {
      vi.mocked(fetch).mockResolvedValue(
        new Response('upstream failure', { status }),
      )
      await expect(checkHealth()).rejects.toMatchObject({
        name: 'ApiError',
        kind: 'http',
        status,
      })
    },
  )

  it('reports network errors separately from HTTP errors', async () => {
    const cause = new TypeError('Failed to fetch')
    vi.mocked(fetch).mockRejectedValue(cause)
    await expect(checkHealth()).rejects.toMatchObject({
      kind: 'network',
      status: null,
      cause,
    })
  })

  it('reports malformed successful JSON', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response('not json'))
    await expect(checkHealth()).rejects.toMatchObject({
      kind: 'response',
      status: 200,
    })
  })

  it('preserves intentional aborts', async () => {
    const controller = new AbortController()
    const error = new DOMException('Aborted', 'AbortError')
    controller.abort()
    vi.mocked(fetch).mockRejectedValue(error)
    await expect(checkHealth(controller.signal)).rejects.toBe(error)
  })

  it('preserves request options and custom headers', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response('{}'))
    await requestJson('/health', {
      cache: 'no-store',
      headers: { 'X-Request-ID': 'test' },
    })
    const options = vi.mocked(fetch).mock.calls[0][1]
    expect(options?.cache).toBe('no-store')
    expect(new Headers(options?.headers).get('X-Request-ID')).toBe('test')
  })

  it('centralizes the existing API routes and encodes IDs', () => {
    expect(API_PATHS.createSearch).toBe('/api/v1/jobs/search')
    expect(API_PATHS.search('a/b')).toBe('/api/v1/jobs/search/a%2Fb')
    expect(API_PATHS.searchResults('abc')).toBe(
      '/api/v1/jobs/search/abc/results',
    )
    expect(API_PATHS.searchEvents('abc')).toBe('/api/v1/jobs/search/abc/events')
    expect(API_PATHS.databaseHealth).toBe('/health/db')
    expect(new ApiError('failure', 'network')).toBeInstanceOf(Error)
  })
})
