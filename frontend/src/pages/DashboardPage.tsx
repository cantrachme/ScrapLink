import { ActiveJobsButton } from '../components/jobs/ActiveJobsButton'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { PageHeader } from '../components/ui/PageHeader'
import { Icon } from '../components/ui/Icon'
import {
  StatusIndicator,
  type ConnectionStatus,
} from '../components/ui/StatusIndicator'
import { checkHealth } from '../lib/api'

export function DashboardPage() {
  const [status, setStatus] = useState<ConnectionStatus>('loading')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    // A reachable but stalled server must not leave the workspace loading forever.
    const timeout = window.setTimeout(() => {
      setStatus('unavailable')
      controller.abort()
    }, 8000)
    checkHealth(controller.signal)
      .then(() => {
        if (!controller.signal.aborted) setStatus('connected')
      })
      .catch(() => {
        if (!controller.signal.aborted) setStatus('unavailable')
      })
      .finally(() => window.clearTimeout(timeout))
    return () => {
      window.clearTimeout(timeout)
      controller.abort()
    }
  }, [attempt])

  return (
    <>
      <PageHeader
        title="Welcome to ScrapLink."
        description="Your next opportunity starts here. Bring your job discovery into one focused workspace."
      />
      <section className="welcome-card" aria-labelledby="welcome-title">
        <div className="welcome-copy">
          <span className="light-eyebrow">
            LESS SEARCHING. MORE POSSIBILITY.
          </span>
          <h2 id="welcome-title">
            Good opportunities.
            <br />
            One place to find them.
          </h2>
          <p>
            Watch Chrome search CareerHub, or search LinkedIn and Wellfound yourself
            and save the jobs that interest you.
          </p>
          <ActiveJobsButton />
          <Link className="button button-light" to="/search">
            Explore Job Search
            <Icon name="arrow" />
          </Link>
        </div>
        <div className="discovery-art" aria-hidden="true">
          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <span className="source-tile tile-linkedin">in</span>
          <span className="art-center">
            <Icon name="search" />
          </span>
          <span className="source-tile tile-wellfound">
            W<span>↗</span>
          </span>
          <span className="art-dot dot-one" />
          <span className="art-dot dot-two" />
        </div>
      </section>
      <div className="dashboard-grid">
        <section
          className="card connection-card"
          aria-labelledby="connection-title"
        >
          <div className="card-title">
            <span className="icon-box">
              <Icon name="server" />
            </span>
            <h2 id="connection-title">Backend connectivity</h2>
          </div>
          <StatusIndicator status={status} />
          <p>
            {status === 'loading'
              ? 'Checking the connection to your ScrapLink backend…'
              : status === 'connected'
                ? 'The ScrapLink API is responding. Your workspace can reach the backend.'
                : 'The backend is not responding. Start FastAPI on port 8000, then check again.'}
          </p>
          <button
            className="text-button"
            disabled={status === 'loading'}
            onClick={() => {
              setStatus('loading')
              setAttempt(attempt + 1)
            }}
          >
            Check connection <span aria-hidden="true">↗</span>
          </button>
          <small>
            API availability only. Database and worker health are not checked.
          </small>
        </section>
        <section
          className="card progress-card"
          aria-labelledby="workspace-title"
        >
          <div className="card-title">
            <span className="icon-box">
              <Icon name="layers" />
            </span>
            <h2 id="workspace-title">Your search workspace</h2>
            <span className="subtle-badge">In development</span>
          </div>
          <div className="empty-state">
            <span className="empty-icon">
              <Icon name="search" />
            </span>
            <div>
              <h3>Room for your next discovery</h3>
              <p>
                Search history and saved results are not connected to this
                dashboard yet. Create a search and follow its live progress.
              </p>
            </div>
          </div>
          <Link className="text-link" to="/search">
            Start a job search
            <Icon name="arrow" />
          </Link>
        </section>
      </div>
      <section className="workflow-section" aria-labelledby="workflow-title">
        <div className="section-heading">
          <h2 id="workflow-title">From search to possibility</h2>
          <span>Your discovery workflow</span>
        </div>
        <ol className="workflow-list">
          <li>
            <span className="step-number">01</span>
            <h3>Set your direction</h3>
            <p>
              Choose a source, keywords, and a location to shape your search.
            </p>
          </li>
          <li>
            <span className="step-number">02</span>
            <h3>Follow the discovery</h3>
            <p>
              See progress as the worker discovers and extracts job listings.
            </p>
          </li>
          <li>
            <span className="step-number">03</span>
            <h3>Explore the details</h3>
            <p>
              Review collected roles, requirements, and links to the original
              listings.
            </p>
          </li>
        </ol>
      </section>
    </>
  )
}
