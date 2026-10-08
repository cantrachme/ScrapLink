import { vi } from 'vitest'
import type { SearchTask } from '../types/search'

export const SEARCH_ID = 'f853d140-493b-42d1-ad75-e7d28924490b'
export const OTHER_ID = '901899d9-bc92-428e-a1d9-f7c5170a2212'
export const task: SearchTask = {
  search_id: SEARCH_ID, status: 'pending',
  request: { source: 'linkedin', keyword: 'Engineer', location: 'United States', date_posted: '24h', max_results: 20 },
  created_at: '2026-10-08T05:00:00Z', updated_at: '2026-10-08T05:00:00Z', error: null,
}
export const summary = { search_id: SEARCH_ID, status: 'completed', source: 'linkedin',
  discovered_urls: [], jobs: [], failures: [], total_discovered: 18, total_extracted: 2, total_failed: 1 }
export const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status })
export class MockEventSource extends EventTarget {
  static instances: MockEventSource[] = []
  readonly url: string
  readyState = 0
  close = vi.fn(() => { this.readyState = 2 })
  addEventListener = vi.fn(super.addEventListener.bind(this))
  removeEventListener = vi.fn(super.removeEventListener.bind(this))
  constructor(url: string) { super(); this.url = url; MockEventSource.instances.push(this) }
  emit(name: string, data: unknown, id: number | string) {
    this.dispatchEvent(new MessageEvent(name, { data: JSON.stringify(data), lastEventId: String(id) }))
  }
  open() { this.readyState = 1; this.dispatchEvent(new Event('open')) }
  disconnect() { this.readyState = 0; this.dispatchEvent(new Event('error')) }
}
export const installEventSource = () => {
  MockEventSource.instances = []
  vi.stubGlobal('EventSource', MockEventSource)
}
export const stream = () => MockEventSource.instances.at(-1)!
export const queued = { search_id: SEARCH_ID, status: 'pending', source: 'linkedin' }
export const started = { ...queued, status: 'running' }
export const page = { page_number: 1, new_jobs_discovered: 18, total_discovered: 18 }
export const extracted = { job_url: 'https://www.linkedin.com/jobs/view/1', title: 'Engineer', company: 'Example', total_extracted: 1 }
export const failure = { job_url: 'https://www.linkedin.com/jobs/view/2', error: 'Job description unavailable', total_failed: 1 }
export const completed = { search_id: SEARCH_ID, status: 'completed', total_discovered: 18, total_extracted: 2, total_failed: 1 }
