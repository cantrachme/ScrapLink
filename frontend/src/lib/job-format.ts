import type { Compensation, JobListing } from '../types/job'

export const NOT_SPECIFIED = 'Not specified'
export const textOrFallback = (value: string | null) => value?.trim() || NOT_SPECIFIED

// Only absolute web links are navigable. Source URLs never become app routes.
export function safeExternalUrl(value: string | null): string | null {
  if (!value || !/^https?:\/\//i.test(value.trim())) return null
  try {
    const url = new URL(value)
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : null
  } catch { return null }
}

export function dateValue(value: string | null): number | null {
  if (!value || !/^\d{4}-\d{2}-\d{2}(?:$|T)/.test(value)) return null
  const day = value.slice(0, 10)
  const calendar = new Date(`${day}T00:00:00Z`)
  if (!Number.isFinite(calendar.getTime()) || calendar.toISOString().slice(0, 10) !== day) return null
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? parsed : null
}
export function postingDate(job: Pick<JobListing, 'posted_at' | 'posted_date'>) {
  return dateValue(job.posted_at) !== null ? job.posted_at : dateValue(job.posted_date) !== null ? job.posted_date : null
}
export function formatDate(value: string | null, includeTime = false): string {
  const timestamp = dateValue(value)
  if (timestamp === null) return NOT_SPECIFIED
  const date = new Date(timestamp)
  // Date-only values must not move to the previous day in western time zones.
  return value?.length === 10 ? date.toLocaleDateString(undefined, { timeZone: 'UTC' }) :
    includeTime ? date.toLocaleString() : date.toLocaleDateString()
}
export function formatCompensation(value: Compensation | null): string | null {
  if (!value) return null
  const { min_amount: min, max_amount: max, currency, period } = value
  const amount = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 20 })
  const range = min !== null && max !== null ? `${amount(min)}–${amount(max)}` :
    min !== null ? `From ${amount(min)}` : max !== null ? `Up to ${amount(max)}` : ''
  return [currency, range, period ? `per ${period}` : ''].filter(Boolean).join(' ') || null
}

// Parse into an inert template, extract text, then let React escape it. No source
// nodes, attributes, scripts, or styles are ever inserted into the live document.
export function descriptionText(value: string): string {
  if (!/<\/?[a-z][^>]*>/i.test(value)) return value
  const template = document.createElement('template')
  template.innerHTML = value
  template.content.querySelectorAll('script, style, iframe, object, embed, template, noscript').forEach((node) => node.remove())
  template.content.querySelectorAll('br').forEach((node) => node.replaceWith('\n'))
  template.content.querySelectorAll('p, div, li, h1, h2, h3, h4, h5, h6, section, article, ul, ol, tr, blockquote, pre').forEach((node) => {
    node.prepend('\n'); node.append('\n')
  })
  return (template.content.textContent || '').replace(/\n[\t ]*\n(?:[\t ]*\n)+/g, '\n\n').trim()
}
