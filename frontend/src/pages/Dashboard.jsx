import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import AppHeader from '../components/AppHeader.jsx'
import Background from '../components/Background.jsx'
import Composer from '../components/Composer.jsx'
import VideoList from '../components/VideoList.jsx'
import ConfirmDialog from '../components/ConfirmDialog.jsx'
import { Chapters, Chat, Download, FileVideo, Search, Sparkle, Trash, Upload, Youtube } from '../components/Icons.jsx'
import { getUsage } from '../services/api.js'
import { deleteEntries, listEntries, onLibraryChange } from '../services/library.js'

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'completed', label: 'Ready' },
  { key: 'processing', label: 'In progress' },
  { key: 'failed', label: 'Failed' },
]

const STEPS = [
  { icon: Youtube, title: 'Drop in a video', body: 'Paste a YouTube link or upload an MP4 from your computer.' },
  { icon: Sparkle, title: 'AI reads every word', body: 'Captions or speech become a clean, timestamped transcript.' },
  { icon: Chapters, title: 'Get the brief', body: 'TL;DR, summary, key points and chapters you can jump through.' },
  { icon: Chat, title: 'Ask & export', body: 'Ask follow-up questions, share the link or download a PDF.' },
]

function matchesFilter(entry, filter) {
  if (filter === 'all') return true
  if (filter === 'processing') return entry.status === 'processing' || entry.status === 'queued'
  return entry.status === filter
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

function SectionHeader({ icon: Icon, title, subtitle, count }) {
  return (
    <div className="mb-6 flex items-end justify-between gap-4">
      <div className="flex items-center gap-4">
        <span className="flex h-11 w-11 items-center justify-center rounded-2xl border border-white/10 bg-gradient-to-b from-white/[0.08] to-transparent text-accent shadow-card">
          <Icon className="h-5 w-5" />
        </span>
        <div>
          <h3 className="font-display text-3xl leading-none text-neutral-50">{title}</h3>
          <p className="mt-1.5 text-[13px] text-neutral-500">{subtitle}</p>
        </div>
      </div>
      <span className="rounded-full border border-white/[0.08] px-3 py-1 font-mono text-xs text-neutral-400">{count}</span>
    </div>
  )
}

function EmptySection({ icon: Icon, text, action, onAction }) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 rounded-3xl border border-dashed border-white/10 bg-white/[0.01] px-6 py-12 text-center">
      <Icon className="h-6 w-6 text-neutral-600" />
      <p className="max-w-xs text-sm text-neutral-500">{text}</p>
      {action && (
        <button type="button" onClick={onAction} className="btn-ghost py-2 text-xs">
          {action}
        </button>
      )}
    </div>
  )
}

export default function Dashboard() {
  const composerRef = useRef(null)
  const [videos, setVideos] = useState([])
  const [loading, setLoading] = useState(true)
  const [usage, setUsage] = useState(null)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const [selecting, setSelecting] = useState(false)
  const [selectedIds, setSelectedIds] = useState(() => new Set())
  const [confirmingBulk, setConfirmingBulk] = useState(false)
  const [pageDrag, setPageDrag] = useState(false)

  const uploadsEnabled = usage?.uploads_enabled ?? true

  const loadVideos = useCallback(async () => {
    setVideos(await listEntries())
    setLoading(false)
  }, [])

  useEffect(() => {
    loadVideos()
    getUsage().then(setUsage).catch(() => {})
    return onLibraryChange(loadVideos)
  }, [loadVideos])

  // Drop a video file anywhere on the page.
  useEffect(() => {
    if (!uploadsEnabled) return undefined
    let depth = 0
    const hasFiles = (e) => Array.from(e.dataTransfer?.types || []).includes('Files')
    const onEnter = (e) => {
      if (!hasFiles(e)) return
      depth += 1
      setPageDrag(true)
    }
    const onLeave = (e) => {
      if (!hasFiles(e)) return
      depth = Math.max(0, depth - 1)
      if (depth === 0) setPageDrag(false)
    }
    const onOver = (e) => hasFiles(e) && e.preventDefault()
    const onDrop = (e) => {
      if (!hasFiles(e)) return
      e.preventDefault()
      depth = 0
      setPageDrag(false)
      const file = e.dataTransfer.files?.[0]
      if (file) {
        window.scrollTo({ top: 0, behavior: 'smooth' })
        composerRef.current?.upload(file)
      }
    }
    window.addEventListener('dragenter', onEnter)
    window.addEventListener('dragleave', onLeave)
    window.addEventListener('dragover', onOver)
    window.addEventListener('drop', onDrop)
    return () => {
      window.removeEventListener('dragenter', onEnter)
      window.removeEventListener('dragleave', onLeave)
      window.removeEventListener('dragover', onOver)
      window.removeEventListener('drop', onDrop)
    }
  }, [uploadsEnabled])

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
    await deleteEntries([...selectedIds])
    stopSelecting()
  }

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    return videos.filter((v) => matchesFilter(v, filter) && (!q || (v.video?.title || '').toLowerCase().includes(q)))
  }, [videos, query, filter])

  const youtube = visible.filter((v) => v.video?.source !== 'upload')
  const uploads = visible.filter((v) => v.video?.source === 'upload')
  const focusComposer = () => window.scrollTo({ top: 0, behavior: 'smooth' })

  return (
    <div className="grain relative min-h-screen">
      <Background />
      <AppHeader>
        <a href="#library" className="btn-quiet hidden sm:inline-flex">
          Library
        </a>
      </AppHeader>

      {/* Hero */}
      <section className="relative">
        <div className="relative mx-auto max-w-4xl px-5 pb-16 pt-20 text-center sm:px-8 sm:pt-28">
          <p className="mx-auto inline-flex animate-fade-up items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-4 py-1.5 text-xs text-neutral-300 backdrop-blur">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
            </span>
            Free · No sign-up · YouTube & MP4
          </p>

          <h1
            className="mt-8 animate-fade-up font-display text-[3.6rem] leading-[0.92] tracking-tight text-neutral-50 sm:text-8xl md:text-[6.5rem]"
            style={{ animationDelay: '80ms' }}
          >
            Watch less.
            <br />
            <span className="text-gradient italic">Understand more.</span>
          </h1>

          <p
            className="mx-auto mt-7 max-w-xl animate-fade-up text-base leading-relaxed text-neutral-400 sm:text-lg"
            style={{ animationDelay: '160ms' }}
          >
            Turn any long video into a crisp brief, timestamped chapters and answers you can trust. Paste a YouTube link
            or drop in your own file.
          </p>

          <div className="mx-auto mt-12 max-w-3xl animate-fade-up text-left" style={{ animationDelay: '240ms' }}>
            <Composer ref={composerRef} uploadsEnabled={uploadsEnabled} maxUploadMb={usage?.max_upload_mb} />
            <p className="mt-4 text-center text-xs text-neutral-600">
              YouTube videos need captions · uploads are transcribed by AI and then deleted
              {usage?.max_video_minutes ? ` · up to ${Math.round(usage.max_video_minutes / 60)} hours long` : ''}
            </p>
          </div>
        </div>

        {/* How it works */}
        <div className="relative mx-auto max-w-6xl px-5 sm:px-8">
          <ol className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map(({ icon: Icon, title, body }, i) => (
              <li
                key={title}
                className="card group animate-fade-up p-6 transition duration-500 hover:-translate-y-1 hover:border-accent/25"
                style={{ animationDelay: `${320 + i * 70}ms` }}
              >
                <div className="flex items-center justify-between">
                  <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent/10 text-accent transition group-hover:bg-accent/20">
                    <Icon className="h-[18px] w-[18px]" />
                  </span>
                  <span className="font-mono text-xs text-neutral-700">0{i + 1}</span>
                </div>
                <p className="mt-5 text-sm font-medium text-neutral-100">{title}</p>
                <p className="mt-1.5 text-[13px] leading-relaxed text-neutral-500">{body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Library */}
      <main id="library" className="relative mx-auto max-w-6xl scroll-mt-20 px-5 py-24 sm:px-8">
        <div className="mb-12 flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="eyebrow">Your library</p>
            <h2 className="mt-3 font-display text-5xl text-neutral-50">Everything you've summarized</h2>
            <p className="mt-2 text-sm text-neutral-500">Saved in this browser — nobody else can see it.</p>
          </div>

          {videos.length > 0 && (
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <div className="relative">
                <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-500" />
                <label htmlFor="video-search" className="sr-only">
                  Search your library
                </label>
                <input
                  id="video-search"
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search"
                  className="input py-2 pl-10 sm:w-48"
                />
              </div>
              <div className="flex flex-wrap gap-1 rounded-full border border-white/[0.08] bg-white/[0.02] p-1" role="group" aria-label="Filter videos">
                {FILTERS.map((f) => (
                  <button
                    key={f.key}
                    type="button"
                    onClick={() => setFilter(f.key)}
                    aria-pressed={filter === f.key}
                    className={`rounded-full px-3 py-1 text-xs transition focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 ${
                      filter === f.key ? 'bg-white text-ink-950' : 'text-neutral-400 hover:text-neutral-100'
                    }`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
              <button
                type="button"
                onClick={() => (selecting ? stopSelecting() : setSelecting(true))}
                className={selecting ? 'btn-primary py-2' : 'btn-ghost py-2'}
              >
                {selecting ? 'Done' : 'Select'}
              </button>
            </div>
          )}
        </div>

        {selecting && (
          <div className="sticky top-20 z-30 mb-8 flex flex-wrap items-center justify-between gap-3 rounded-full border border-white/10 bg-ink-900/90 py-2 pl-5 pr-2 shadow-card backdrop-blur-xl">
            <p className="text-sm text-neutral-300">{selectedIds.size ? `${selectedIds.size} selected` : 'Tap videos to select them'}</p>
            <div className="flex flex-wrap items-center gap-1">
              <button type="button" onClick={() => setSelectedIds(new Set(visible.map((v) => v.id)))} className="btn-quiet text-xs">
                Select all
              </button>
              {selectedIds.size > 0 && (
                <button type="button" onClick={() => setSelectedIds(new Set())} className="btn-quiet text-xs">
                  Clear
                </button>
              )}
              <button
                type="button"
                onClick={() => setConfirmingBulk(true)}
                disabled={!selectedIds.size}
                className="btn bg-rose-500 px-4 py-2 text-xs text-white hover:bg-rose-400 focus-visible:ring-rose-400/60"
              >
                <Trash className="h-3.5 w-3.5" />
                Remove{selectedIds.size ? ` ${selectedIds.size}` : ''}
              </button>
            </div>
          </div>
        )}

        {loading ? (
          <LibrarySkeleton />
        ) : (
          <div className="space-y-20">
            <section aria-label="YouTube videos">
              <SectionHeader icon={Youtube} title="YouTube videos" subtitle="Summarized from a YouTube link" count={youtube.length} />
              {youtube.length ? (
                <VideoList entries={youtube} onDelete={(id) => deleteEntries([id])} selecting={selecting} selectedIds={selectedIds} onToggleSelect={toggleSelect} />
              ) : (
                <EmptySection
                  icon={Youtube}
                  text={videos.length ? 'No YouTube videos match this view.' : 'Paste a YouTube link above and your briefs will appear here.'}
                  action={videos.length ? null : 'Paste a link'}
                  onAction={focusComposer}
                />
              )}
            </section>

            {uploadsEnabled && (
              <section aria-label="Your uploads">
                <SectionHeader icon={FileVideo} title="Your uploads" subtitle="MP4 and other files from your computer" count={uploads.length} />
                {uploads.length ? (
                  <VideoList entries={uploads} onDelete={(id) => deleteEntries([id])} selecting={selecting} selectedIds={selectedIds} onToggleSelect={toggleSelect} />
                ) : (
                  <EmptySection
                    icon={Upload}
                    text={videos.length ? 'No uploads match this view.' : 'Upload a video file and its brief — with PDF export — will appear here.'}
                    action={videos.length ? null : 'Upload a video'}
                    onAction={focusComposer}
                  />
                )}
              </section>
            )}
          </div>
        )}
      </main>

      {pageDrag && (
        <div className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center bg-ink-950/80 backdrop-blur-md">
          <div className="glow-border rounded-[2.5rem]">
            <div className="flex flex-col items-center gap-4 rounded-[2.5rem] bg-ink-900/90 px-16 py-14">
              <span className="flex h-16 w-16 animate-float items-center justify-center rounded-2xl bg-accent/15 text-accent">
                <Download className="h-7 w-7" />
              </span>
              <p className="font-display text-4xl text-neutral-50">Drop to summarize</p>
              <p className="text-sm text-neutral-500">MP4, MOV, WEBM, MKV or AVI</p>
            </div>
          </div>
        </div>
      )}

      {confirmingBulk && (
        <ConfirmDialog
          title={`Remove ${selectedIds.size} video${selectedIds.size > 1 ? 's' : ''}?`}
          description="They're only removed from this browser's library."
          confirmLabel="Remove"
          onCancel={() => setConfirmingBulk(false)}
          onConfirm={handleBulkDelete}
        />
      )}

      <footer className="relative border-t border-white/[0.06] py-12 text-center text-xs text-neutral-600">
        VidMind · Free summaries, chapters and answers for long videos
      </footer>
    </div>
  )
}
