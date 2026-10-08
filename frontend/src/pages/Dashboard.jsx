import { useCallback, useEffect, useMemo, useState } from 'react'
import AppHeader from '../components/AppHeader.jsx'
import Omnibox from '../components/Omnibox.jsx'
import VideoList from '../components/VideoList.jsx'
import ConfirmDialog from '../components/ConfirmDialog.jsx'
import { Chapters, Chat, Lock, Search, Trash } from '../components/Icons.jsx'
import { deleteVideo, getVideos } from '../services/api.js'
import { videoTitle } from '../utils/format.js'
import { useAuth } from '../auth/AuthProvider.jsx'

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'completed', label: 'Ready' },
  { key: 'processing', label: 'In progress' },
  { key: 'youtube', label: 'YouTube' },
  { key: 'upload', label: 'Uploads' },
  { key: 'failed', label: 'Failed' },
]

const FEATURES = [
  { icon: Chapters, title: 'Summary & chapters', body: 'A clear brief, key takeaways and timestamped chapters.' },
  { icon: Chat, title: 'Ask anything', body: 'Answers grounded in the video, with sources you can jump to.' },
]
const LOCAL_FEATURE = { icon: Lock, title: 'Private by design', body: 'Transcription and AI run on your machine. Nothing leaves it.' }
const ACCOUNT_FEATURE = { icon: Lock, title: 'Your private library', body: 'Only you can see the videos you analyze and their notes.' }

function matchesFilter(video, filter) {
  if (filter === 'all') return true
  if (filter === 'processing') return video.status === 'processing' || video.status === 'uploaded'
  if (filter === 'upload' || filter === 'youtube') return video.source_type === filter
  return video.status === filter
}

function LibrarySkeleton() {
  return (
    <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
      {[0, 1, 2].map((i) => (
        <div key={i} className="card overflow-hidden">
          <div className="skeleton aspect-video rounded-none" />
          <div className="space-y-3 p-5">
            <div className="skeleton h-3 w-24" />
            <div className="skeleton h-4 w-4/5" />
            <div className="skeleton h-3 w-3/5" />
          </div>
        </div>
      ))}
    </div>
  )
}

export default function Dashboard() {
  const { authEnabled, account, refreshAccount } = useAuth()
  const features = [...FEATURES, authEnabled ? ACCOUNT_FEATURE : LOCAL_FEATURE]
  const uploadsEnabled = account?.uploads_enabled ?? true
  const [videos, setVideos] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const [selecting, setSelecting] = useState(false)
  const [selectedIds, setSelectedIds] = useState(() => new Set())
  const [confirmingBulk, setConfirmingBulk] = useState(false)
  const [bulkDeleting, setBulkDeleting] = useState(false)

  const loadVideos = useCallback(async () => {
    try {
      const data = await getVideos()
      setVideos(data.videos)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadVideos()
  }, [loadVideos])

  const handleDelete = async (videoId) => {
    try {
      await deleteVideo(videoId)
      setVideos((prev) => prev.filter((v) => v.id !== videoId))
      refreshAccount()
    } catch (err) {
      setError(err.message)
    }
  }

  const toggleSelect = useCallback((id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const stopSelecting = () => {
    setSelecting(false)
    setSelectedIds(new Set())
  }

  const handleBulkDelete = async () => {
    setConfirmingBulk(false)
    setBulkDeleting(true)
    const ids = [...selectedIds]
    const results = await Promise.allSettled(ids.map((id) => deleteVideo(id)))
    const deleted = new Set(ids.filter((_, i) => results[i].status === 'fulfilled'))
    setVideos((prev) => prev.filter((v) => !deleted.has(v.id)))
    const failed = ids.length - deleted.size
    setError(failed ? `${failed} video${failed > 1 ? 's' : ''} couldn't be deleted.` : null)
    setBulkDeleting(false)
    stopSelecting()
  }

  const filteredVideos = useMemo(() => {
    const q = query.trim().toLowerCase()
    return videos.filter(
      (v) => matchesFilter(v, filter) && (!q || videoTitle(v).toLowerCase().includes(q))
    )
  }, [videos, query, filter])

  return (
    <div className="grain min-h-screen">
      <AppHeader>
        <a href="#library" className="btn-quiet hidden sm:inline-flex">
          Library
        </a>
        {!authEnabled && (
          <span className="hidden items-center gap-2 rounded-full border border-white/[0.08] px-3 py-1.5 text-[11px] text-neutral-400 sm:inline-flex">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
            Runs locally
          </span>
        )}
      </AppHeader>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="bg-grid pointer-events-none absolute inset-0" />
        <div className="pointer-events-none absolute left-1/2 top-[-12rem] h-[34rem] w-[60rem] -translate-x-1/2 rounded-full bg-[radial-gradient(closest-side,rgba(139,108,255,0.22),transparent)]" />
        <div className="pointer-events-none absolute left-[70%] top-24 h-64 w-64 rounded-full bg-gold/10 blur-3xl" />

        <div className="relative mx-auto max-w-3xl px-5 pb-20 pt-20 text-center sm:px-8 sm:pt-28">
          <p className="mx-auto inline-flex animate-fade-up items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3.5 py-1.5 text-xs text-neutral-400 backdrop-blur">
            <Lock className="h-3.5 w-3.5 text-accent" />
            {authEnabled ? 'Video intelligence for long-form content' : 'Private video intelligence, on your machine'}
          </p>

          <h1
            className="mt-7 animate-fade-up font-display text-[3.4rem] leading-[0.95] tracking-tight text-neutral-50 sm:text-7xl md:text-[5.5rem]"
            style={{ animationDelay: '60ms' }}
          >
            Watch less.
            <br />
            <span className="text-gradient italic">Understand more.</span>
          </h1>

          <p
            className="mx-auto mt-6 max-w-xl animate-fade-up text-base leading-relaxed text-neutral-400 sm:text-lg"
            style={{ animationDelay: '120ms' }}
          >
            Turn any long video into a crisp brief, timestamped chapters and answers you can
            trust — in about a minute.
          </p>

          <div className="mt-10 animate-fade-up text-left" style={{ animationDelay: '180ms' }}>
            <Omnibox uploadsEnabled={uploadsEnabled} onStarted={refreshAccount} />
            <p className="mt-3 text-center text-xs text-neutral-600">
              {uploadsEnabled
                ? 'Public YouTube videos · MP4, MOV, MKV, WEBM or AVI up to 500 MB'
                : 'Any public YouTube video with captions'}
              {account?.max_video_minutes ? ` · up to ${account.max_video_minutes} min` : ''}
            </p>
          </div>
        </div>

        <div className="relative mx-auto grid max-w-5xl grid-cols-1 gap-px overflow-hidden border-y border-white/[0.06] bg-white/[0.06] sm:grid-cols-3 sm:rounded-3xl sm:border">
          {features.map(({ icon: Icon, title, body }) => (
            <div key={title} className="bg-ink-950/90 p-6 backdrop-blur">
              <Icon className="h-[18px] w-[18px] text-accent" />
              <p className="mt-4 text-sm font-medium text-neutral-100">{title}</p>
              <p className="mt-1 text-[13px] leading-relaxed text-neutral-500">{body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Library */}
      <main id="library" className="relative mx-auto max-w-6xl scroll-mt-20 px-5 py-20 sm:px-8">
        <div className="mb-8 flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="eyebrow">Library</p>
            <h2 className="mt-2 font-display text-4xl text-neutral-50">
              Your videos
              {videos.length > 0 && (
                <span className="ml-3 align-middle font-mono text-sm text-neutral-600">
                  {videos.length}
                </span>
              )}
            </h2>
          </div>

          {videos.length > 0 && (
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <div className="relative">
                <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-500" />
                <label htmlFor="video-search" className="sr-only">
                  Search your videos
                </label>
                <input
                  id="video-search"
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search library"
                  className="input py-2 pl-10 sm:w-56"
                />
              </div>
              <button
                type="button"
                onClick={() => (selecting ? stopSelecting() : setSelecting(true))}
                className={selecting ? 'btn-primary py-2' : 'btn-ghost py-2'}
              >
                {selecting ? 'Done' : 'Select'}
              </button>
              <div
                className="flex flex-wrap gap-1 rounded-full border border-white/[0.08] bg-white/[0.02] p-1"
                role="group"
                aria-label="Filter videos"
              >
                {FILTERS.map((f) => (
                  <button
                    key={f.key}
                    type="button"
                    onClick={() => setFilter(f.key)}
                    aria-pressed={filter === f.key}
                    className={`rounded-full px-3 py-1 text-xs transition focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 ${
                      filter === f.key
                        ? 'bg-white text-ink-950'
                        : 'text-neutral-400 hover:text-neutral-100'
                    }`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {selecting && (
          <div className="sticky top-20 z-30 mb-6 flex flex-wrap items-center justify-between gap-3 rounded-full border border-white/10 bg-ink-900/90 py-2 pl-5 pr-2 shadow-card backdrop-blur-xl">
            <p className="text-sm text-neutral-300">
              {selectedIds.size ? `${selectedIds.size} selected` : 'Tap videos to select them'}
            </p>
            <div className="flex flex-wrap items-center gap-1">
              <button
                type="button"
                onClick={() =>
                  setSelectedIds(new Set(videos.filter((v) => v.status === 'completed').map((v) => v.id)))
                }
                className="btn-quiet text-xs"
              >
                Select all summarized
              </button>
              <button
                type="button"
                onClick={() => setSelectedIds(new Set(filteredVideos.map((v) => v.id)))}
                className="btn-quiet text-xs"
              >
                Select all shown
              </button>
              {selectedIds.size > 0 && (
                <button type="button" onClick={() => setSelectedIds(new Set())} className="btn-quiet text-xs">
                  Clear
                </button>
              )}
              <button
                type="button"
                onClick={() => setConfirmingBulk(true)}
                disabled={!selectedIds.size || bulkDeleting}
                className="btn bg-rose-500 px-4 py-2 text-xs text-white hover:bg-rose-400 focus-visible:ring-rose-400/60"
              >
                <Trash className="h-3.5 w-3.5" />
                {bulkDeleting ? 'Deleting…' : `Delete${selectedIds.size ? ` ${selectedIds.size}` : ''}`}
              </button>
            </div>
          </div>
        )}

        {error && (
          <p role="alert" className="mb-6 rounded-2xl border border-rose-400/20 bg-rose-500/5 px-4 py-3 text-sm text-rose-300">
            {error}
          </p>
        )}

        {loading ? (
          <LibrarySkeleton />
        ) : videos.length === 0 && error ? null : videos.length === 0 ? (
          <div className="card flex flex-col items-center px-6 py-16 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.03]">
              <Chapters className="h-6 w-6 text-accent" />
            </div>
            <p className="mt-6 font-display text-3xl text-neutral-100">Nothing here yet</p>
            <p className="mt-2 max-w-sm text-sm leading-relaxed text-neutral-500">
              {uploadsEnabled
                ? 'Paste a YouTube link or drop a video above. Your briefs, chapters and answers will collect here.'
                : 'Paste a YouTube link above. Your briefs, chapters and answers will collect here.'}
            </p>
            <button
              type="button"
              onClick={() => {
                window.scrollTo({ top: 0, behavior: 'smooth' })
                setTimeout(() => document.getElementById('omnibox-url')?.focus(), 400)
              }}
              className="btn-primary mt-7"
            >
              Analyze your first video
            </button>
          </div>
        ) : filteredVideos.length === 0 ? (
          <div className="card px-6 py-14 text-center text-sm text-neutral-500">
            No videos match this view.
          </div>
        ) : (
          <VideoList
            videos={filteredVideos}
            onDelete={handleDelete}
            onRetried={loadVideos}
            selecting={selecting}
            selectedIds={selectedIds}
            onToggleSelect={toggleSelect}
          />
        )}
      </main>

      {confirmingBulk && (
        <ConfirmDialog
          title={`Delete ${selectedIds.size} video${selectedIds.size > 1 ? 's' : ''}?`}
          description="Their transcripts, summaries, chapters and search indexes will be removed too. This can't be undone."
          confirmLabel="Delete"
          onCancel={() => setConfirmingBulk(false)}
          onConfirm={handleBulkDelete}
        />
      )}

      <footer className="border-t border-white/[0.06] py-10 text-center text-xs text-neutral-600">
        {authEnabled
          ? 'VidMind · Summaries, chapters and answers from long videos'
          : 'VidMind · Transcription, summaries and answers generated locally'}
      </footer>
    </div>
  )
}
