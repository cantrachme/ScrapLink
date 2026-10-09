import type { DatePosted, SearchTask, TaskStatus } from '../types/search'

export const DATE_LABELS: Record<DatePosted, string> = {
  any: 'Any time', '24h': 'Past 24 hours', '7d': 'Past 7 days', '30d': 'Past 30 days',
}
export const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)
export const isCount = (value: unknown): value is number =>
  typeof value === 'number' && Number.isSafeInteger(value) && value >= 0
export const isSearchId = (value: unknown): value is string =>
  typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)
export const isTaskStatus = (value: unknown): value is TaskStatus =>
  typeof value === 'string' && ['pending', 'running', 'completed', 'failed'].includes(value)
export const isTerminal = (status: TaskStatus) => status === 'completed' || status === 'failed'
const isDate = (value: unknown) => typeof value === 'string' && Number.isFinite(Date.parse(value))

export function isSearchTask(value: unknown): value is SearchTask {
  if (!isRecord(value) || !isRecord(value.request)) return false
  const r = value.request
  return isSearchId(value.search_id) && isTaskStatus(value.status) &&
    isDate(value.created_at) && isDate(value.updated_at) &&
    (value.error === null || typeof value.error === 'string') &&
    typeof r.source === 'string' && ['linkedin', 'wellfound', 'careerhub'].includes(r.source) &&
    typeof r.keyword === 'string' && (r.mode === 'active_jobs' ? r.keyword === '' && r.location === '' : r.keyword.trim().length > 0) && r.keyword.length <= 200 &&
    typeof r.location === 'string' && r.location.length <= 200 &&
    typeof r.date_posted === 'string' && Object.hasOwn(DATE_LABELS, r.date_posted) &&
    isCount(r.max_results) && r.max_results >= 1 && r.max_results <= 500
}
