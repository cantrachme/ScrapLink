import { useEffect } from 'react'

export function PageHeader({
  title,
  description,
  eyebrow = 'YOUR WORKSPACE',
}: {
  title: string
  description: string
  eyebrow?: string
}) {
  useEffect(() => {
    document.title = `${title} · ScrapLink`
  }, [title])
  return (
    <div className="page-heading">
      <p className="eyebrow">{eyebrow}</p>
      <h1>{title}</h1>
      <p className="page-description">{description}</p>
    </div>
  )
}
