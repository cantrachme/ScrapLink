import type { SearchEvent, SearchEventName } from '../types/event'
import { isCount, isRecord } from './search-contract'

export const SEARCH_EVENT_NAMES: SearchEventName[] = [
  'browser_action', 'search_queued', 'search_started', 'page_discovered', 'job_extracted',
  'job_failed', 'search_completed', 'search_failed',
]
const BROWSER_ACTIONS: Record<string, string> = {
  opened_source: 'Chrome opened the selected website',
  focused_keyword: 'Clicked the keyword search box',
  typed_keyword: 'Typed your exact keyword',
  location_filter_local: 'This source has no location input; location will be filtered from inspected listings',
  submitted_search: 'Clicked Apply filters',
  inspected_results: 'Inspected real search results',
  scrolled_listing: 'Scrolled to a job listing',
  opened_listing: 'Clicked and opened a job listing',
  inspected_description: 'Inspected the job description',
  returned_results: 'Returned to search results',
  filtered_job: 'Excluded listing by your location or posting date filter',
  manual_required: 'Opened Chrome for your manual search. Enter your keyword and location there, then save jobs below. Automated collection is unavailable for this source.',
}
const publicUrl = (value: unknown) => {
  if (typeof value !== 'string') return false
  try {
    const url = new URL(value)
    return ['http:', 'https:'].includes(url.protocol) && !!url.hostname && !url.username && !url.password
  } catch { return false }
}
const plainText = (value: unknown) => typeof value === 'string' && value.length <= 500 && !/[<>]/.test(value)

export function parseSearchEvent(name: SearchEventName, message: MessageEvent, searchId: string): SearchEvent | null {
  if (!/^[1-9]\d{0,9}$/.test(message.lastEventId) || Number(message.lastEventId) > 2147483647) return null
  try {
    const d: unknown = JSON.parse(message.data)
    if (!isRecord(d)) return null
    let valid = false
    let keys: string[] = []
    switch (name) {
      case 'browser_action':
        keys = ['action']
        valid = typeof d.action === 'string' && Object.hasOwn(BROWSER_ACTIONS, d.action)
        break
      case 'search_queued':
      case 'search_started':
        keys = ['search_id', 'status', 'source']
        valid = d.search_id === searchId && d.status === (name === 'search_queued' ? 'pending' : 'running') && typeof d.source === 'string'
        break
      case 'page_discovered':
        keys = ['page_number', 'new_jobs_discovered', 'total_discovered']
        valid = isCount(d.page_number) && d.page_number >= 1 && isCount(d.new_jobs_discovered) && isCount(d.total_discovered)
        break
      case 'job_extracted':
        keys = ['job_url', 'title', 'company', 'total_extracted']
        valid = publicUrl(d.job_url) && plainText(d.title) && plainText(d.company) && isCount(d.total_extracted) && d.total_extracted >= 1
        break
      case 'job_failed':
        keys = ['job_url', 'error', 'total_failed']
        valid = publicUrl(d.job_url) && typeof d.error === 'string' && ['Job detail fetching or extraction failed', 'Job description unavailable'].includes(d.error) && isCount(d.total_failed) && d.total_failed >= 1
        break
      case 'search_completed':
        keys = ['search_id', 'status', 'total_discovered', 'total_extracted', 'total_failed']
        valid = d.search_id === searchId && d.status === 'completed' && isCount(d.total_discovered) && isCount(d.total_extracted) && isCount(d.total_failed)
        break
      case 'search_failed':
        keys = ['search_id', 'status', 'error']
        valid = d.search_id === searchId && d.status === 'failed' && typeof d.error === 'string' && ['Search execution failed', 'Browser execution failed'].includes(d.error)
    }
    if (!valid || Object.keys(d).some((key) => !keys.includes(key))) return null
    return { id: message.lastEventId, event: name, data: d } as unknown as SearchEvent
  } catch { return null }
}

export function activityMessage(event: SearchEvent): string {
  switch (event.event) {
    case 'browser_action': return BROWSER_ACTIONS[event.data.action]
    case 'search_queued': return 'Search queued'
    case 'search_started': return 'Search started'
    case 'page_discovered': return `Listing page ${event.data.page_number} processed — ${event.data.new_jobs_discovered} new jobs discovered`
    case 'job_extracted': return `Job extracted — ${event.data.title || 'Untitled role'}${event.data.company ? ` · ${event.data.company}` : ''}`
    case 'job_failed': return `Job extraction failed — ${event.data.error}`
    case 'search_completed': return 'Search completed'
    case 'search_failed': return `Search failed — ${event.data.error}`
  }
}
