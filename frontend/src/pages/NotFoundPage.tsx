import { Link } from 'react-router'
import { PageHeader } from '../components/ui/PageHeader'

export function NotFoundPage() {
  return (
    <>
      <PageHeader
        title="Page not found"
        eyebrow="404 · A LITTLE OFF TRACK"
        description="This page doesn’t exist. Your workspace is still right here."
      />
      <Link className="button button-primary" to="/">
        Back to Dashboard
      </Link>
    </>
  )
}
