import type { PersistedJob } from '../types/job'

export const JOB_ID = 'e853d140-493b-42d1-ad75-e7d28924490b'
export const job: PersistedJob = {
  id: JOB_ID, source: 'linkedin', source_job_id: '123', job_url: 'https://example.com/jobs/123',
  application_url: null, title: 'Python Engineer', company: 'Example', company_url: null,
  location: null, workplace_type: null, employment_type: null, seniority_level: null,
  description: null, responsibilities: [], requirements: [], skills: [],
  experience_min_years: null, experience_max_years: null, compensation: null,
  posted_date: null, posted_at: null, posted_text: null, status: 'unknown',
  first_seen_at: '2026-10-08T05:00:00Z', last_verified_at: null, updated_at: '2026-10-08T05:00:00Z',
}
export function makeJob(index: number, fields: Partial<PersistedJob> = {}): PersistedJob {
  return { ...job, id: `e853d140-493b-42d1-ad75-${String(index).padStart(12, '0')}`, title: `Role ${String(index).padStart(3, '0')}`, ...fields }
}
