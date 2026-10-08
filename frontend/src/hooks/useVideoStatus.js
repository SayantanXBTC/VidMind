import { useEffect, useState } from 'react'
import { getVideoStatus } from '../services/api.js'

const POLL_INTERVAL_MS = 3000
const MAX_BACKOFF_MS = 30000

/**
 * Polls GET /api/videos/{id}/status every few seconds until completed/failed.
 * A failed poll (network blip, rate limit, deploy restart) doesn't stop
 * polling; it backs off and tries again, so progress never freezes.
 */
export default function useVideoStatus(videoId, { active, initialStatus, initialProgress } = {}) {
  const [status, setStatus] = useState(initialStatus ?? null)
  const [progress, setProgress] = useState(initialProgress ?? 0)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!active || !videoId) return undefined

    let cancelled = false
    let timer
    let failures = 0

    const poll = async () => {
      try {
        const data = await getVideoStatus(videoId)
        if (cancelled) return
        failures = 0
        setStatus(data.status)
        setProgress(data.progress)
        setError(data.error)
        if (data.status === 'processing' || data.status === 'uploaded') {
          timer = setTimeout(poll, POLL_INTERVAL_MS)
        }
      } catch (err) {
        if (cancelled) return
        failures += 1
        setError(failures >= 3 ? err.message : null)
        timer = setTimeout(poll, Math.min(POLL_INTERVAL_MS * 2 ** failures, MAX_BACKOFF_MS))
      }
    }

    poll()

    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [videoId, active])

  return { status, progress, error }
}
