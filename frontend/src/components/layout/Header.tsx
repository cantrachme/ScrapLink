import { matchPath, useLocation } from 'react-router'
import { Icon } from '../ui/Icon'

export function Header({
  mobileOpen,
  onToggleMenu,
}: {
  mobileOpen: boolean
  onToggleMenu: () => void
}) {
  const { pathname } = useLocation()
  const title =
    pathname === '/'
      ? 'Dashboard'
      : matchPath('/search', pathname)
        ? 'Job Search'
        : matchPath('/searches/:searchId', pathname)
          ? 'Search Details'
          : matchPath('/jobs/:jobId', pathname)
            ? 'Job Details'
            : 'Page not found'
  return (
    <header className="app-header">
      <div className="header-context">
        <button
          className="menu-button"
          aria-label={mobileOpen ? 'Close navigation' : 'Open navigation'}
          aria-expanded={mobileOpen}
          aria-controls="workspace-navigation"
          onClick={onToggleMenu}
        >
          <Icon name="menu" />
        </button>
        <span className="header-workspace">Workspace</span>
        <span className="header-divider" aria-hidden="true">
          /
        </span>
        <strong>{title}</strong>
      </div>
      <span className="preview-label">MVP preview</span>
    </header>
  )
}
