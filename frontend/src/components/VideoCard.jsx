import { useState } from 'react'
import { Link } from 'react-router-dom'
import StatusBadge from './StatusBadge.jsx'
import ProgressBar from './ProgressBar.jsx'
import ConfirmDialog from './ConfirmDialog.jsx'
import { USAGE_CHANGED } from './AppHeader.jsx'
import { Check, Retry, Trash, Youtube } from './Icons.jsx'
import useJob from '../hooks/useJob.js'
import { analyzeVideo } from '../services/api.js'
import { saveEntry } from '../services/library.js'
import { formatRelativeDate, formatTimestamp } from '../utils/format.js'

const ACTIVE = new Set(['queued', 'processing'])

export default function VideoCard({ entry, onDelete, index = 0, selecting = false, selected = false, onToggleSelect }) {
  const [restarted, setRestarted] = useState(false)
  const { job } = useJob(entry.id, { active: restarted || ACTIVE.has(entry.status) })
  const status = job?.status ?? entry.status
  const progress = job?.progress ?? 5
  const stage = job?.stage ?? 'Queued'
  const error = job?.error ?? entry.error

  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [retryError, setRetryError] = useState(null)

  const { video } = entry
  const title = video?.title || 'YouTube video'
  const href = `/videos/${entry.id}`

  const handleRetry = async () => {
    setRetrying(true)
    setRetryError(null)
    try {
      const fresh = await analyzeVideo(video.url)
      await saveEntry({ id: fresh.id, video: fresh.video, status: fresh.status, error: fresh.error })
      window.dispatchEvent(new Event(USAGE_CHANGED))
      setRestarted(true)
    } catch (err) {
      setRetryError(err.message)
    } finally {
      setRetrying(false)
    }
  }

  return (
    <article
      className={`card card-hover group relative flex animate-fade-up flex-col overflow-hidden ${
        selected ? 'border-accent/60 ring-2 ring-accent/40' : ''
      }`}
      style={{ animationDelay: `${Math.min(index, 8) * 50}ms` }}
    >
      {selecting && (
        // In selection mode the whole card toggles selection instead of opening the video.
        <button
          type="button"
          onClick={() => onToggleSelect?.(entry.id)}
          aria-pressed={selected}
          aria-label={`${selected ? 'Deselect' : 'Select'} ${title}`}
          className="absolute inset-0 z-20 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/60"
        >
          <span
            className={`absolute right-3 top-3 flex h-6 w-6 items-center justify-center rounded-full border transition ${
              selected ? 'border-accent bg-accent text-ink-950' : 'border-white/40 bg-black/50 text-transparent backdrop-blur'
            }`}
          >
            <Check className="h-3.5 w-3.5" strokeWidth={2.6} />
          </span>
        </button>
      )}

      <Link
        to={href}
        tabIndex={-1}
        aria-hidden="true"
        className="relative block aspect-video overflow-hidden border-b border-white/[0.06] bg-ink-850"
      >
        {video?.thumbnail && (
          <img
            src={video.thumbnail}
            alt=""
            loading="lazy"
            className="h-full w-full object-cover transition duration-700 group-hover:scale-[1.03]"
          />
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-ink-950/80 via-transparent to-transparent" />
        <StatusBadge status={status} className="absolute left-3 top-3" />
        {video?.duration ? (
          <span className="absolute bottom-3 right-3 rounded-md bg-black/70 px-1.5 py-0.5 font-mono text-[11px] tabular-nums text-neutral-200 backdrop-blur">
            {formatTimestamp(video.duration)}
          </span>
        ) : null}
      </Link>

      <div className="flex flex-1 flex-col p-5">
        <div className="flex items-center gap-2 text-[11px] text-neutral-500">
          <Youtube className="h-3.5 w-3.5" />
          <span>YouTube</span>
          <span className="text-neutral-700">·</span>
          <span>{formatRelativeDate(entry.savedAt)}</span>
        </div>

        <Link
          to={href}
          className="mt-2 line-clamp-2 text-[15px] font-medium leading-snug text-neutral-100 transition-colors after:absolute after:inset-0 hover:text-white focus:outline-none focus-visible:underline"
        >
          {title}
        </Link>

        {status === 'completed' && entry.result?.tldr && (
          <p className="mt-2 line-clamp-2 text-[13px] leading-relaxed text-neutral-500">{entry.result.tldr}</p>
        )}

        {ACTIVE.has(status) && <ProgressBar progress={progress} label={stage} className="mt-4" />}

        {status === 'failed' && (
          <div className="relative z-10 mt-4 flex items-center justify-between gap-3">
            <p className="line-clamp-2 text-xs text-rose-300/90">{retryError || error || 'Analysis failed.'}</p>
            <button type="button" onClick={handleRetry} disabled={retrying} className="btn-ghost shrink-0 px-3 py-1.5 text-xs">
              <Retry className="h-3.5 w-3.5" />
              {retrying ? 'Retrying…' : 'Retry'}
            </button>
          </div>
        )}
      </div>

      <div className="relative z-10 flex items-center justify-between border-t border-white/[0.06] px-5 py-3">
        <Link
          to={href}
          className="text-xs font-medium text-neutral-300 transition hover:text-white focus:outline-none focus-visible:underline"
        >
          {status === 'completed' ? 'Open brief' : 'View'}
        </Link>
        <button
          type="button"
          onClick={() => setConfirmingDelete(true)}
          aria-label={`Remove ${title}`}
          className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs text-neutral-500 transition hover:bg-rose-500/10 hover:text-rose-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-rose-400/60"
        >
          <Trash className="h-3.5 w-3.5" />
          Remove
        </button>
      </div>

      {confirmingDelete && (
        <ConfirmDialog
          title="Remove from your library?"
          description="It's only removed from this browser. You can analyze the video again any time."
          confirmLabel="Remove"
          onCancel={() => setConfirmingDelete(false)}
          onConfirm={() => {
            setConfirmingDelete(false)
            onDelete(entry.id)
          }}
        />
      )}
    </article>
  )
}
