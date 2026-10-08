import { Link, useParams } from 'react-router'
import { PageHeader } from '../components/ui/PageHeader'
import { Icon } from '../components/ui/Icon'

export function SearchDetailsPage() {
  const { searchId } = useParams()
  return (
    <>
      <PageHeader
        title="Search Details"
        description="A dedicated space for search progress and collected results."
      />
      <section className="card detail-placeholder">
        <span className="empty-icon">
          <Icon name="layers" />
        </span>
        <span className="subtle-badge">Coming in Steps 48–49</span>
        <h2>The full picture, in one place</h2>
        <p>
          Live progress and detailed results will appear here when the search
          workflow is connected.
        </p>
        <dl className="reference">
          <dt>Requested search ID</dt>
          <dd>{searchId}</dd>
        </dl>
        <p className="placeholder-note">
          This preview does not load or verify the requested search.
        </p>
        <Link className="button button-primary" to="/search">
          Back to Job Search
          <Icon name="arrow" />
        </Link>
      </section>
    </>
  )
}
