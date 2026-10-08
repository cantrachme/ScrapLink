export const API_PATHS = {
  health: '/health',
  databaseHealth: '/health/db',
  createSearch: '/api/v1/jobs/search',
  search: (searchId: string) =>
    `/api/v1/jobs/search/${encodeURIComponent(searchId)}`,
  searchResults: (searchId: string) => `${API_PATHS.search(searchId)}/results`,
  searchEvents: (searchId: string) => `${API_PATHS.search(searchId)}/events`,
} as const

export interface HealthResponse {
  status: string
  service: string
  environment: string
  version: string
}

export class ApiError extends Error {
  readonly status: number | null
  readonly kind: 'http' | 'network' | 'response'

  constructor(
    message: string,
    kind: ApiError['kind'],
    status: number | null = null,
    cause?: unknown,
  ) {
    super(message, { cause })
    this.name = 'ApiError'
    this.kind = kind
    this.status = status
  }
}

// Same-origin URLs deliberately use Vite's proxy in development and the
// deployment reverse proxy in production. Never put server secrets here.
export async function requestJson<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers)
  headers.set('Accept', 'application/json')
  let response: Response
  try {
    response = await fetch(path, { ...options, headers })
  } catch (error) {
    if (options.signal?.aborted) throw error
    throw new ApiError('Unable to reach the backend.', 'network', null, error)
  }
  if (!response.ok) {
    throw new ApiError(
      `Request failed (HTTP ${response.status}).`,
      'http',
      response.status,
    )
  }
  try {
    return (await response.json()) as T
  } catch (error) {
    if (options.signal?.aborted) throw error
    throw new ApiError(
      'The backend returned an invalid JSON response.',
      'response',
      response.status,
      error,
    )
  }
}

export function checkHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return requestJson<HealthResponse>(API_PATHS.health, { signal })
}
