// Payloads from backend/app/schemas/search_event.py; see docs/search-events.md.
export interface SearchQueued {
  search_id: string
  status: 'pending'
  source: string
}
export interface SearchStarted {
  search_id: string
  status: 'running'
  source: string
}
export interface PageDiscovered {
  page_number: number
  new_jobs_discovered: number
  total_discovered: number
}
export interface JobExtracted {
  job_url: string
  title: string
  company: string
  total_extracted: number
}
export interface JobFailed {
  job_url: string
  error:
    'Job detail fetching or extraction failed' | 'Job description unavailable'
  total_failed: number
}
export interface SearchCompleted {
  search_id: string
  status: 'completed'
  total_discovered: number
  total_extracted: number
  total_failed: number
}
export interface SearchFailed {
  search_id: string
  status: 'failed'
  error: 'Search execution failed' | 'Browser execution failed'
}
export interface SearchEventPayloadMap {
  search_queued: SearchQueued
  search_started: SearchStarted
  page_discovered: PageDiscovered
  job_extracted: JobExtracted
  job_failed: JobFailed
  search_completed: SearchCompleted
  search_failed: SearchFailed
}
export type SearchEventName = keyof SearchEventPayloadMap
// Parsed SSE envelope: id is the per-search sequence serialized as text.
// The database timestamp is not part of the wire payload.
export type SearchEvent = {
  [Name in SearchEventName]: {
    id: string
    event: Name
    data: SearchEventPayloadMap[Name]
  }
}[SearchEventName]
