import { useState } from 'react'
import { Link } from 'react-router-dom'
import StatusBadge from './StatusBadge.jsx'
import ProgressBar from './ProgressBar.jsx'
import ConfirmDialog from './ConfirmDialog.jsx'
import { Check, Film, Retry, Trash, Youtube } from './Icons.jsx'
import useVideoStatus from '../hooks/useVideoStatus.js'
import { retryVideo } from '../services/api.js'
import { stageLabel } from '../utils/stage.js'
import { formatFileSize, formatRelativeDate, formatTimestamp, videoTitle } from '../utils/format.js'

function Thumbnail({ video }) {
  if (video.source_type === 'youtube' && video.source_thumbnail) {
    return (
      <img
        src={video.source_thumbnail}
        alt=""
        loading="lazy"
        className="h-full w-full object-cover transition duration-700 group-hover:scale-[1.03]"
      />
    )
  }
  return (
    <div className="flex h-full w-full items-center justify-center bg-[radial-gradient(circle_at_30%_20%,rgba(139,108,255,0.28),transparent_55%),radial-gradient(circle_at_80%_90%,rgba(242,210,155,0.12),transparent_50%)]">
      <Film className="h-8 w-8 text-white/30" strokeWidth={1.3} />
    </div>
  )
}

export default function VideoCard({
  video,
  onDelete,
  onRetried,
  index = 0,
  selecting = false,
  selected = false,
  onToggleSelect,
}) {
  const [justRetried, setJustRetried] = useState(false)
  const isActive = justRetried || video.status === 'processing' || video.status === 'uploaded'
  const { status, progress } = useVideoStatus(video.id, {
    active: isActive,
    initialStatus: justRetried ? 'processing' : video.status,
    initialProgress: justRetried ? 5 : video.processing_progress,
  })

  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [retryError, setRetryError] = useState(null)

  const handleRetry = async () => {
    setRetrying(true)
    setRetryError(null)
    try {
      await retryVideo(video.id)
      setJustRetried(true)
      onRetried?.(video.id)
    } catch (err) {
      setRetryError(err.message)
    } finally {
      setRetrying(false)
    }
  }

  const isYoutube = video.source_type === 'youtube'
  const title = videoTitle(video)
  const href = `/videos/${video.id}`

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
          onClick={() => onToggleSelect?.(video.id)}
          aria-pressed={selected}
          aria-label={`${selected ? 'Deselect' : 'Select'} ${title}`}
          className="absolute inset-0 z-20 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/60"
        >
          <span
            className={`absolute right-3 top-3 flex h-6 w-6 items-center justify-center rounded-full border transition ${
              selected
                ? 'border-accent bg-accent text-ink-950'
                : 'border-white/40 bg-black/50 text-transparent backdrop-blur'
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
        <Thumbnail video={video} />
        <div className="absolute inset-0 bg-gradient-to-t from-ink-950/80 via-transparent to-transparent" />
        <StatusBadge status={status} className="absolute left-3 top-3" />
        {video.duration ? (
          <span className="absolute bottom-3 right-3 rounded-md bg-black/70 px-1.5 py-0.5 font-mono text-[11px] tabular-nums text-neutral-200 backdrop-blur">
            {formatTimestamp(video.duration)}
          </span>
        ) : null}
      </Link>

      <div className="flex flex-1 flex-col p-5">
        <div className="flex items-center gap-2 text-[11px] text-neutral-500">
          {isYoutube ? <Youtube className="h-3.5 w-3.5" /> : <Film className="h-3.5 w-3.5" />}
          <span>{isYoutube ? 'YouTube' : 'Upload'}</span>
          <span className="text-neutral-700">·</span>
          <span>{formatRelativeDate(video.created_at)}</span>
          {!isYoutube && formatFileSize(video.file_size) && (
            <>
              <span className="text-neutral-700">·</span>
              <span>{formatFileSize(video.file_size)}</span>
            </>
          )}
        </div>

        <Link
          to={href}
          className="mt-2 line-clamp-2 text-[15px] font-medium leading-snug text-neutral-100 transition-colors after:absolute after:inset-0 hover:text-white focus:outline-none focus-visible:underline"
        >
          {title}
        </Link>

        {status === 'completed' && video.tldr && (
          <p className="mt-2 line-clamp-2 text-[13px] leading-relaxed text-neutral-500">{video.tldr}</p>
        )}

        {status === 'processing' && (
          <ProgressBar
            progress={progress}
            label={stageLabel(progress, video.source_type)}
            className="mt-4"
          />
        )}

        {status === 'failed' && (
          <div className="relative z-10 mt-4 flex items-center justify-between gap-3">
            <p className="text-xs text-rose-300/90">{retryError || 'Processing failed.'}</p>
            <button
              type="button"
              onClick={handleRetry}
              disabled={retrying}
              className="btn-ghost px-3 py-1.5 text-xs"
            >
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
          aria-label={`Delete ${title}`}
          className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs text-neutral-500 transition hover:bg-rose-500/10 hover:text-rose-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-rose-400/60"
        >
          <Trash className="h-3.5 w-3.5" />
          Delete
        </button>
      </div>

      {confirmingDelete && (
        <ConfirmDialog
          title="Delete this video?"
          description="Its transcript, summary, chapters and search index will be removed too."
          confirmLabel="Delete"
          onCancel={() => setConfirmingDelete(false)}
          onConfirm={() => {
            setConfirmingDelete(false)
            onDelete(video.id)
          }}
        />
      )}
    </article>
  )
}
