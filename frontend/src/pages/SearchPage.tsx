import { Icon } from '../components/ui/Icon'
import { PageHeader } from '../components/ui/PageHeader'

export function SearchPage() {
  return (
    <>
      <PageHeader
        title="Job Search"
        eyebrow="DISCOVER YOUR NEXT MOVE"
        description="A focused search, across the sources you know. Start with a direction and explore the possibilities."
      />
      <section aria-labelledby="sources-title">
        <div className="section-heading">
          <h2 id="sources-title">Two sources. A wider perspective.</h2>
          <span>Supported by the backend</span>
        </div>
        <div className="source-grid">
          <article className="card source-card">
            <span className="source-logo linkedin-logo" aria-hidden="true">
              in
            </span>
            <h3>LinkedIn</h3>
            <p>
              Explore professional roles across companies, industries, and
              locations.
            </p>
            <span className="source-label">Professional opportunities</span>
          </article>
          <article className="card source-card">
            <span className="source-logo wellfound-logo" aria-hidden="true">
              W↗
            </span>
            <h3>Wellfound</h3>
            <p>Discover opportunities with startups and growing teams.</p>
            <span className="source-label">Startup opportunities</span>
          </article>
        </div>
      </section>
      <section
        className="card search-placeholder"
        aria-labelledby="search-builder-title"
      >
        <span className="empty-icon">
          <Icon name="search" />
        </span>
        <span className="subtle-badge">Coming in Step 48</span>
        <h2 id="search-builder-title">Your search starts here. Soon.</h2>
        <p>
          We’re building the search workflow. Source selection, keywords,
          location, date filters, and result limits will live here, with live
          progress once a search begins.
        </p>
        <div className="planned-controls" aria-label="Planned search controls">
          <span>Source selection</span>
          <span>Keywords & location</span>
          <span>Date filters</span>
          <span>Result limit</span>
        </div>
        <p className="placeholder-note">
          Search submission is not available in this preview.
        </p>
      </section>
    </>
  )
}
