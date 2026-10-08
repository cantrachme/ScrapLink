const paths = {
  grid: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  search: 'M21 21l-5-5 M18 10.5a7.5 7.5 0 1 1-15 0 7.5 7.5 0 0 1 15 0',
  arrow: 'M4 12h16 M14 6l6 6-6 6',
  layers: 'M12 3l10 6-10 6L2 9z M2 14l10 6 10-6',
  link: 'M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-2 2 M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l2-2',
  menu: 'M4 6h16 M4 12h16 M4 18h16',
  panel: 'M3 4h18v16H3z M9 4v16',
  server: 'M3 3h18v7H3z M3 14h18v7H3z M7 6.5h.01 M7 17.5h.01',
  clock: 'M12 7v5l3 2 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
} as const

export function Icon({
  name,
  className = '',
}: {
  name: keyof typeof paths
  className?: string
}) {
  return (
    <svg
      className={`icon ${className}`}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name]} />
    </svg>
  )
}
