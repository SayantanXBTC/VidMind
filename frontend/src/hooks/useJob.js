import { useEffect, useState } from 'react'
import { getVideo } from '../services/api.js'
import { saveEntry } from '../services/library.js'

const POLL_INTERVAL_MS = 2500
const MAX_BACKOFF_MS = 30000

/**
 * Follows an analysis job until it finishes, then stores the result in the
 * browser library. A failed poll (network blip, rate limit, server restart)
 * backs off and retries instead of freezing the progress bar.
 *
 * Returns { job, error }. `job` is null until the first response.
 */
export default function useJob(videoId, { active = true, initialJob = null } = {}) {
  const [job, setJob] = useState(initialJob)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!active || !videoId) return undefined
    let cancelled = false
    let timer
    let failures = 0

    const poll = async () => {
      try {
        const lite = await getVideo(videoId, { includeResult: false })
        if (cancelled) return
        failures = 0
        setError(null)
        if (lite.status === 'completed') {
          const full = await getVideo(videoId)
          if (cancelled) return
          setJob(full)
          await saveEntry({ id: full.id, video: full.video, status: 'completed', result: full.result, error: null })
          return
        }
        setJob(lite)
        if (lite.status === 'failed') {
          await saveEntry({ id: lite.id, video: lite.video, status: 'failed', error: lite.error })
          return
        }
        timer = setTimeout(poll, POLL_INTERVAL_MS)
      } catch (err) {
        if (cancelled) return
        if (err.status === 404) {
          // Server no longer has it (e.g. restarted mid-analysis).
          setJob((prev) => (prev ? { ...prev, status: 'failed', error: 'This analysis was interrupted. Try again.' } : prev))
          return
        }
        failures += 1
        if (failures >= 3) setError(err.message)
        timer = setTimeout(poll, Math.min(POLL_INTERVAL_MS * 2 ** failures, MAX_BACKOFF_MS))
      }
    }

    poll()
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [videoId, active])

  return { job, error }
}
