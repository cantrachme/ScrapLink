import type { PersistedJob } from '../types/job'
import { isRecord, isSearchId } from './search-contract'

export const SOURCE_LABELS = { linkedin: 'LinkedIn', wellfound: 'Wellfound', realpython_demo: 'Real Python demo' }
export const WORKPLACE_LABELS = { remote: 'Remote', hybrid: 'Hybrid', onsite: 'Onsite' }
export const EMPLOYMENT_LABELS = { full_time: 'Full time', part_time: 'Part time', contract: 'Contract', internship: 'Internship', temporary: 'Temporary', other: 'Other' }
const nullableString = (v: unknown) => v === null || typeof v === 'string'
const nullableNumber = (v: unknown) => v === null || (typeof v === 'number' && Number.isFinite(v) && v >= 0)
const stringList = (v: unknown) => Array.isArray(v) && v.every((item) => typeof item === 'string')
const member = (v: unknown, labels: object) => typeof v === 'string' && Object.hasOwn(labels, v)

export function isPersistedJob(v: unknown): v is PersistedJob {
  if (!isRecord(v)) return false
  const c = v.compensation
  return isSearchId(v.id) && member(v.source, SOURCE_LABELS) &&
    ['title', 'company', 'job_url', 'first_seen_at', 'updated_at'].every((key) => typeof v[key] === 'string' && v[key].trim().length > 0) &&
    ['source_job_id', 'application_url', 'company_url', 'location', 'seniority_level', 'description', 'posted_at', 'posted_date', 'posted_text', 'last_verified_at'].every((key) => nullableString(v[key])) &&
    (v.workplace_type === null || member(v.workplace_type, WORKPLACE_LABELS)) &&
    (v.employment_type === null || member(v.employment_type, EMPLOYMENT_LABELS)) &&
    ['responsibilities', 'requirements', 'skills'].every((key) => stringList(v[key])) &&
    nullableNumber(v.experience_min_years) && nullableNumber(v.experience_max_years) &&
    typeof v.status === 'string' && ['active', 'closed', 'unknown'].includes(v.status) &&
    (c === null || (isRecord(c) && nullableString(c.raw_text) && nullableString(c.currency) &&
      nullableNumber(c.min_amount) && nullableNumber(c.max_amount) &&
      (c.period === null || ['hour', 'month', 'year'].includes(String(c.period)))))
}
