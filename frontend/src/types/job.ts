// JSON response contracts from backend/app/schemas/job.py.
// Defaulted response fields are serialized by FastAPI; nullable is not optional.
export type JobSource = 'linkedin' | 'wellfound' | 'careerhub' | 'realpython_demo'
export type JobStatus = 'active' | 'closed' | 'unknown'
export type WorkplaceType = 'remote' | 'hybrid' | 'onsite'
export type EmploymentType =
  'full_time' | 'part_time' | 'contract' | 'internship' | 'temporary' | 'other'

export interface Compensation {
  raw_text: string | null
  currency: string | null
  min_amount: number | null
  max_amount: number | null
  period: 'hour' | 'month' | 'year' | null
}

export interface JobListing {
  source: JobSource
  source_job_id: string | null
  job_url: string
  application_url: string | null
  title: string
  company: string
  company_url: string | null
  location: string | null
  workplace_type: WorkplaceType | null
  employment_type: EmploymentType | null
  seniority_level: string | null
  description: string | null
  responsibilities: string[]
  requirements: string[]
  skills: string[]
  experience_min_years: number | null
  experience_max_years: number | null
  compensation: Compensation | null
  posted_date: string | null // ISO date
  posted_at: string | null // ISO datetime
  posted_text: string | null
  status: JobStatus
  first_seen_at: string
  last_verified_at: string | null
}

export interface JobExtractionFailure {
  source?: JobSource | null
  job_url: string
  error: string
}

// Read-only database identity; never required from browser collectors.
export interface PersistedJob extends JobListing {
  id: string
  updated_at: string
}
