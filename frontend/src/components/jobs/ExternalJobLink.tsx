import type { ReactNode } from 'react'
import { safeExternalUrl } from '../../lib/job-format'

export function ExternalJobLink({ url, children }: { url: string | null; children: ReactNode }) {
  const href = safeExternalUrl(url)
  return href ? <a className="text-link" href={href} target="_blank" rel="noopener noreferrer">{children}<span aria-hidden="true">↗</span></a> : null
}
