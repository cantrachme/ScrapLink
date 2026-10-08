import { Link, useParams } from 'react-router'
import { PageHeader } from '../components/ui/PageHeader'
import { Icon } from '../components/ui/Icon'

export function JobDetailsPage() {
  const { jobId } = useParams()
  return (
    <>
      <PageHeader
        title="Job Details"
        description="Get to know an opportunity beyond its title."
      />
      <section className="card detail-placeholder">
        <span className="empty-icon">
          <Icon name="link" />
        </span>
        <span className="subtle-badge">Coming in Step 49</span>
        <h2>The details that matter</h2>
        <p>
          This space is reserved for a role’s description, requirements,
          compensation, and original listing.
        </p>
        <dl className="reference">
          <dt>Requested job ID</dt>
          <dd>{jobId}</dd>
        </dl>
        <p className="placeholder-note">
          This preview does not load or verify the requested job.
        </p>
        <Link className="button button-primary" to="/search">
          Back to Job Search
          <Icon name="arrow" />
        </Link>
      </section>
    </>
  )
}
