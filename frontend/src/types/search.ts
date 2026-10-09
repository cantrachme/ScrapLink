import type { JobExtractionFailure, PersistedJob, JobSource } from './job'

export type SearchSource = Extract<JobSource, 'linkedin' | 'wellfound' | 'careerhub'>
export type DatePosted = 'any' | '24h' | '7d' | '30d'
export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed'

// Defaulted request properties may be omitted; none accepts null.
export interface JobSearchRequest {
  mode?: 'search' | 'active_jobs'
  source?: SearchSource // default: linkedin
  keyword: string // 1–200 characters, nonempty after trimming
  location?: string // default: United States; max 200 characters
  date_posted?: DatePosted // default: 24h
  watch_mode?: boolean
  watch_delay_seconds?: number
  max_results?: number // integer 1–500; default: 50
}

export interface JobSearchResponse {
  search_id: string
  status: string // The response schema intentionally uses an unrestricted string.
  message: string
}

// SearchTask is defined in backend/app/services/task_manager.py.
export interface SearchTask {
  search_id: string
  status: TaskStatus
  request: Required<Omit<JobSearchRequest, 'watch_mode' | 'watch_delay_seconds' | 'mode'>> & Pick<JobSearchRequest, 'watch_mode' | 'watch_delay_seconds' | 'mode'>
  created_at: string
  updated_at: string
  error: string | null
}

export interface JobSearchResultsResponse {
  source_statuses?: Record<string, string>
  search_id: string
  status: string
  source: JobSource | null
  discovered_urls: string[]
  jobs: PersistedJob[]
  failures: JobExtractionFailure[]
  total_discovered: number
  total_extracted: number
  total_failed: number
}
