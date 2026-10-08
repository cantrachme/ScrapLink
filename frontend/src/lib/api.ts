import type { PersistedJob } from '../types/job'
import { isPersistedJob, SOURCE_LABELS } from './job-contract'
import type { JobSearchRequest, JobSearchResponse, JobSearchResultsResponse, SearchTask } from '../types/search'
import { isCount, isRecord, isSearchId, isSearchTask, isTaskStatus } from './search-contract'

export const API_PATHS = {
  job: (jobId: string) => `/api/v1/jobs/${encodeURIComponent(jobId)}`,
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
  readonly kind: 'http' | 'network' | 'response' | 'timeout'

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
  const controller = new AbortController()
  const abort = () => controller.abort(options.signal?.reason)
  options.signal?.addEventListener('abort', abort, { once: true })
  if (options.signal?.aborted) abort()
  let timedOut = false
  const timeout = window.setTimeout(() => {
    timedOut = true
    controller.abort()
  }, 15000)
  try {
    let response: Response
    try {
      response = await fetch(path, { ...options, headers, signal: controller.signal })
    } catch (error) {
      if (controller.signal.aborted) throw error
      throw new ApiError('Unable to reach the backend. Check the connection and try again.', 'network', null, error)
    }
    if (!response.ok) {
      let detail = ''
      try {
        const body: unknown = await response.json()
        if (isRecord(body)) {
          if (typeof body.detail === 'string') detail = body.detail
          else if (Array.isArray(body.detail)) {
            detail = body.detail.filter(isRecord).map((item) => {
              const field = Array.isArray(item.loc) ? item.loc.filter((part) => part !== 'body').join('.') : ''
              return typeof item.msg === 'string' ? `${field ? `${field}: ` : ''}${item.msg}` : ''
            }).filter(Boolean).join('; ')
          }
        }
      } catch { /* Proxies can return non-JSON errors. Keep the HTTP status. */ }
      throw new ApiError(detail || `Request failed (HTTP ${response.status}).`, 'http', response.status)
    }
    try {
      return (await response.json()) as T
    } catch (error) {
      if (controller.signal.aborted) throw error
      throw new ApiError('The backend returned an invalid JSON response.', 'response', response.status, error)
    }
  } catch (error) {
    if (timedOut) throw new ApiError('The request timed out. The backend may still have accepted a submitted search.', 'timeout')
    throw error
  } finally {
    window.clearTimeout(timeout)
    options.signal?.removeEventListener('abort', abort)
  }
}

export function checkHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return requestJson<HealthResponse>(API_PATHS.health, { signal })
}

const invalidResponse = () => new ApiError('The backend returned missing or malformed search fields.', 'response')

export async function createJobSearch(request: JobSearchRequest, signal?: AbortSignal): Promise<JobSearchResponse> {
  const value = await requestJson<unknown>(API_PATHS.createSearch, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request), signal,
  })
  if (!isRecord(value) || !isSearchId(value.search_id) || !isTaskStatus(value.status) || typeof value.message !== 'string') {
    throw invalidResponse()
  }
  return { search_id: value.search_id, status: value.status, message: value.message }
}

export async function getJobSearch(searchId: string, signal?: AbortSignal): Promise<SearchTask> {
  const value = await requestJson<unknown>(API_PATHS.search(searchId), { signal })
  if (!isSearchTask(value) || value.search_id.toLowerCase() !== searchId.toLowerCase()) throw invalidResponse()
  return value
}

// Step 48 consumes only the persisted summary, not unvalidated job records.
export interface SearchResultsSummary {
  search_id: string
  status: string
  total_discovered: number
  total_extracted: number
  total_failed: number
}
export async function getSearchResultsSummary(searchId: string, signal?: AbortSignal): Promise<SearchResultsSummary> {
  const v = await requestJson<unknown>(API_PATHS.searchResults(searchId), { signal })
  if (!isRecord(v) || v.search_id !== searchId || !isTaskStatus(v.status) ||
    !isCount(v.total_discovered) || !isCount(v.total_extracted) || !isCount(v.total_failed)) throw invalidResponse()
  return { search_id: searchId, status: v.status, total_discovered: v.total_discovered,
    total_extracted: v.total_extracted, total_failed: v.total_failed }
}

export async function getSearchResults(searchId: string, signal?: AbortSignal): Promise<JobSearchResultsResponse> {
  if (!isSearchId(searchId)) throw new ApiError('Invalid search ID.', 'response')
  const v = await requestJson<unknown>(API_PATHS.searchResults(searchId), { signal })
  if (!isRecord(v) || !isSearchId(v.search_id) || v.search_id.toLowerCase() !== searchId.toLowerCase() ||
    !isTaskStatus(v.status) || !isCount(v.total_discovered) || !isCount(v.total_extracted) || !isCount(v.total_failed) ||
    !(v.source === null || (typeof v.source === 'string' && Object.hasOwn(SOURCE_LABELS, v.source))) ||
    !Array.isArray(v.jobs) || !v.jobs.every(isPersistedJob) ||
    !Array.isArray(v.discovered_urls) || !v.discovered_urls.every((url) => typeof url === 'string') ||
    !Array.isArray(v.failures) || !v.failures.every((f) => isRecord(f) && typeof f.job_url === 'string' && typeof f.error === 'string')) {
    throw new ApiError('The backend returned missing or malformed job results.', 'response')
  }
  return v as unknown as JobSearchResultsResponse
}

export async function getJobById(jobId: string, signal?: AbortSignal): Promise<PersistedJob> {
  if (!isSearchId(jobId)) throw new ApiError('Invalid job ID.', 'response')
  const v = await requestJson<unknown>(API_PATHS.job(jobId), { signal })
  if (!isPersistedJob(v) || v.id.toLowerCase() !== jobId.toLowerCase()) {
    throw new ApiError('The backend returned missing or malformed job fields.', 'response')
  }
  return v
}
