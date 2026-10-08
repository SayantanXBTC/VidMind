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

export function formatFileSize(bytes) {
  if (!bytes) return null
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

export function formatRelativeDate(isoString) {
  // SQLite drops the timezone, so the API returns UTC times without an offset.
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(isoString)
  const date = new Date(hasZone ? isoString : `${isoString}Z`)
  const diffSeconds = (Date.now() - date.getTime()) / 1000
  if (diffSeconds < 60) return 'Just now'
  if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)} min ago`
  if (diffSeconds < 86400) return `${Math.floor(diffSeconds / 3600)} h ago`
  if (diffSeconds < 86400 * 7) return `${Math.floor(diffSeconds / 86400)} d ago`
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

export function videoTitle(video) {
  if (!video) return ''
  if (video.source_title) return video.source_title
  return video.original_filename.replace(/\.[a-z0-9]{2,4}$/i, '')
}
