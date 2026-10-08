export function formatTimestamp(seconds) {
  const total = Math.max(0, Math.floor(seconds || 0))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const mm = String(m).padStart(2, '0')
  const ss = String(s).padStart(2, '0')
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
}

export function formatDuration(seconds) {
  if (!seconds && seconds !== 0) return null
  const total = Math.round(seconds)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  if (h) return `${h}h ${m}m`
  if (m) return `${m} min`
  return `${total}s`
}

export function formatRelativeDate(value) {
  // Accepts epoch milliseconds or an ISO string (UTC if it has no offset).
  let date
  if (typeof value === 'number') date = new Date(value)
  else {
    const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(value)
    date = new Date(hasZone ? value : `${value}Z`)
  }
  if (Number.isNaN(date.getTime())) return ''
  const diffSeconds = (Date.now() - date.getTime()) / 1000
  if (diffSeconds < 60) return 'Just now'
  if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)} min ago`
  if (diffSeconds < 86400) return `${Math.floor(diffSeconds / 3600)} h ago`
  if (diffSeconds < 86400 * 7) return `${Math.floor(diffSeconds / 86400)} d ago`
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}
