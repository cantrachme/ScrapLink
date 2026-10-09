import { useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { requestJson } from '../../lib/api'
import { isRecord, isSearchId } from '../../lib/search-contract'
import { Icon } from '../ui/Icon'

import { readActiveOptions, type ActiveOptions } from '../../lib/active-options'

export function ActiveJobsButton({ onStarted, options, label = 'Active Jobs' }: {
  onStarted?: () => void; options?: ActiveOptions; label?: string
}) {
  const navigate = useNavigate()
  const pending = useRef(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function start() {
    if (pending.current) return
    pending.current = true; setBusy(true); setError('')
    try {
      const result = await requestJson<unknown>('/api/v1/jobs/active', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(options ?? readActiveOptions()),
      })
      if (!isRecord(result) || !isSearchId(result.search_id)) throw new Error('The backend returned an invalid discovery ID.')
      navigate(`/active-jobs/${result.search_id}`)
      onStarted?.()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not start Active Jobs.') }
    finally { pending.current = false; setBusy(false) }
  }
  return <>
    <button className="button active-jobs-button" title={label} aria-label={label} disabled={busy} onClick={start}>
      <Icon name="layers" /><span className="sidebar-label">{busy ? 'Starting…' : label}</span>
    </button>
    {error && <p className="error-banner" role="alert">{error}</p>}
  </>
}
