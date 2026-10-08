export type ConnectionStatus = 'loading' | 'connected' | 'unavailable'

const labels: Record<ConnectionStatus, string> = {
  loading: 'Loading',
  connected: 'Connected',
  unavailable: 'Unavailable',
}

export function StatusIndicator({ status }: { status: ConnectionStatus }) {
  return (
    <span className={`status status-${status}`} role="status">
      <span className="status-dot" />
      {labels[status]}
    </span>
  )
}
