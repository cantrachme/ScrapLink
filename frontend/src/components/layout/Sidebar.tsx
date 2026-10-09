import { ActiveJobsButton } from '../jobs/ActiveJobsButton'
import { NavLink } from 'react-router'
import { Icon } from '../ui/Icon'

interface SidebarProps {
  collapsed: boolean
  mobileOpen: boolean
  onNavigate: () => void
  onCollapse: () => void
}

export function Sidebar({
  collapsed,
  mobileOpen,
  onNavigate,
  onCollapse,
}: SidebarProps) {
  return (
    <aside
      className={`sidebar ${mobileOpen ? 'mobile-open' : ''}`}
      aria-label="Workspace sidebar"
    >
      <NavLink
        to="/"
        className="brand"
        aria-label="ScrapLink dashboard"
        onClick={onNavigate}
      >
        <span className="brand-mark">
          <Icon name="link" />
        </span>
        <span className="sidebar-label">
          ScrapLink<span className="brand-period">.</span>
        </span>
      </NavLink>
      <div className="sidebar-nav" id="workspace-navigation">
        <p className="nav-caption sidebar-label">WORKSPACE</p>
        <nav aria-label="Main navigation">
          <NavLink
            to="/"
            end
            onClick={onNavigate}
            aria-label="Dashboard"
            title="Dashboard"
          >
            <Icon name="grid" />
            <span className="sidebar-label">Dashboard</span>
          </NavLink>
          <NavLink
            to="/search"
            onClick={onNavigate}
            aria-label="Job Search"
            title="Job Search"
          >
            <Icon name="search" />
            <span className="sidebar-label">Job Search</span>
          </NavLink>
          <ActiveJobsButton onStarted={onNavigate} />
        </nav>
        <div className="reserved-navigation sidebar-label">
          <p className="nav-caption">SEARCH WORKSPACE</p>
          <p>
            <Icon name="layers" />
            Search details
          </p>
          <p>
            <Icon name="link" />
            Job details
          </p>
          <span>Available from your future search results.</span>
        </div>
      </div>
      <div className="sidebar-bottom">
        <div className="workspace-note sidebar-label">
          <span className="workspace-badge">S</span>
          <div>
            <strong>Your workspace</strong>
            <small>Job discovery, simplified</small>
          </div>
        </div>
        <button
          className="collapse-button"
          onClick={onCollapse}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-expanded={!collapsed}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          <Icon name="panel" />
          <span className="sidebar-label">Collapse sidebar</span>
        </button>
      </div>
    </aside>
  )
}
