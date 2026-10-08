import { useEffect, useRef, useState } from 'react'
import { Outlet, useLocation } from 'react-router'
import { Header } from './Header'
import { Sidebar } from './Sidebar'

export function AppLayout() {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const { pathname } = useLocation()
  const previousPath = useRef(pathname)
  const main = useRef<HTMLElement>(null)

  useEffect(() => {
    if (mobileOpen) {
      document
        .querySelector<HTMLAnchorElement>('#workspace-navigation nav a')
        ?.focus()
    }
  }, [mobileOpen])

  useEffect(() => {
    if (previousPath.current !== pathname) {
      main.current?.focus()
      previousPath.current = pathname
    }
  }, [pathname])

  return (
    <div
      className={`app-shell ${collapsed ? 'sidebar-collapsed' : ''}`}
      onKeyDown={(event) => {
        if (event.key === 'Escape' && mobileOpen) {
          setMobileOpen(false)
          document.querySelector<HTMLButtonElement>('.menu-button')?.focus()
        }
      }}
    >
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <Sidebar
        collapsed={collapsed}
        mobileOpen={mobileOpen}
        onNavigate={() => {
          setMobileOpen(false)
          if (mobileOpen) main.current?.focus()
        }}
        onCollapse={() => setCollapsed(!collapsed)}
      />
      <div className="main-column">
        <Header
          mobileOpen={mobileOpen}
          onToggleMenu={() => setMobileOpen(!mobileOpen)}
        />
        <main id="main-content" ref={main} tabIndex={-1}>
          <Outlet />
        </main>
        <footer className="app-footer">
          <span>ScrapLink</span>
          <span>A more focused way to find your next opportunity.</span>
        </footer>
      </div>
    </div>
  )
}
