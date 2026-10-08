import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import AppHeader, { USAGE_CHANGED } from '../components/AppHeader.jsx'
import StatusBadge from '../components/StatusBadge.jsx'
import ProcessingTimeline from '../components/ProcessingTimeline.jsx'
import ConfirmDialog from '../components/ConfirmDialog.jsx'
import AskVideo from '../components/AskVideo.jsx'
import Player from '../components/Player.jsx'
import { ArrowLeft, ArrowUpRight, Check, Copy, Link as LinkIcon, Retry, Search, Trash, Youtube } from '../components/Icons.jsx'
import useJob from '../hooks/useJob.js'
import { analyzeVideo, getVideo, youtubeUrl } from '../services/api.js'
import { deleteEntries, getEntry, saveEntry } from '../services/library.js'
import { formatDuration, formatTimestamp } from '../utils/format.js'

const TABS = [
  { key: 'brief', label: 'Brief' },
  { key: 'ask', label: 'Ask' },
  { key: 'transcript', label: 'Transcript' },
]
const ACTIVE = new Set(['queued', 'processing'])
const VIDEO_ID_RE = /^[A-Za-z0-9_-]{11}$/

const LANGUAGE_NAMES = typeof Intl.DisplayNames === 'function' ? new Intl.DisplayNames(['en'], { type: 'language' }) : null
function languageName(code) {
  if (!code) return null
  try {
    return LANGUAGE_NAMES?.of(code) || code
  } catch {
    return code
  }
}

// Caption lines are only a few seconds long; merge them into readable paragraphs.
function buildParagraphs(segments, targetSeconds = 25) {
  const paragraphs = []
  let current = null
  for (const seg of segments) {
    if (!current) current = { start: seg.start, end: seg.end, text: seg.text }
    else {
      current.text += ` ${seg.text}`
      current.end = seg.end
    }
    const length = current.end - current.start
    if ((length >= targetSeconds && /[.!?]$/.test(seg.text.trim())) || length >= targetSeconds * 1.6) {
      paragraphs.push(current)
      current = null
    }
  }
  if (current) paragraphs.push(current)
  return paragraphs
}

function highlightMatch(text, query) {
  const q = query.trim()
  if (!q) return text
  const parts = text.split(new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'))
  return parts.map((part, i) =>
    part.toLowerCase() === q.toLowerCase() ? (
      <mark key={i} className="rounded bg-accent/25 px-0.5 text-white">
        {part}
      </mark>
    ) : (
      part
    )
  )
}

function briefAsMarkdown(video, result) {
  const lines = [`# ${video.title || 'Video brief'}`, '', video.url, '']
  if (result.tldr) lines.push(`> ${result.tldr}`, '')
  lines.push('## Summary', '', result.summary, '')
  if (result.key_points.length) lines.push('## Key points', '', ...result.key_points.map((p) => `- ${p}`), '')
  if (result.chapters.length) {
    lines.push('## Chapters', '', ...result.chapters.map((c) => `- ${formatTimestamp(c.start)} ${c.title}`))
  }
  return lines.join('\n')
}

function Skeleton({ lines = 5 }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="skeleton h-3" style={{ width: `${90 - i * 9}%` }} />
      ))}
    </div>
  )
}

export default function VideoDetails() {
  const { videoId } = useParams()
  const navigate = useNavigate()
  const playerRef = useRef(null)

  const [entry, setEntry] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [polling, setPolling] = useState(false)
  const [tab, setTab] = useState('brief')
  const [query, setQuery] = useState('')
  const [currentTime, setCurrentTime] = useState(0)
  const [confirmingRemove, setConfirmingRemove] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [copied, setCopied] = useState(null) // 'brief' | 'link'

  // 1. This browser's library → 2. the server's cache → 3. start a new analysis
  //    (that's how a shared link opens for someone who never saw the video).
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setLoadError(null)
    setPolling(false)
    ;(async () => {
      if (!VIDEO_ID_RE.test(videoId)) {
        setLoadError("That doesn't look like a YouTube video link.")
        setLoading(false)
        return
      }
      const local = await getEntry(videoId)
      if (cancelled) return
      if (local?.status === 'completed' && local.result) {
        setEntry(local)
        setLoading(false)
        return
      }
      try {
        let job
        try {
          job = await getVideo(videoId)
        } catch (err) {
          if (err.status !== 404) throw err
          job = await analyzeVideo(youtubeUrl(videoId))
          window.dispatchEvent(new Event(USAGE_CHANGED))
        }
        if (cancelled) return
        const next = { id: job.id, video: job.video, status: job.status, result: job.result ?? undefined, error: job.error }
        await saveEntry(next)
        setEntry(next)
        setPolling(ACTIVE.has(job.status))
      } catch (err) {
        if (!cancelled) setLoadError(err.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [videoId])

  const { job, error: pollError } = useJob(videoId, { active: polling })
  useEffect(() => {
    if (!job) return
    setEntry((prev) => ({ ...prev, ...job, result: job.result ?? prev?.result }))
    if (!ACTIVE.has(job.status)) setPolling(false)
  }, [job])

  const status = entry?.status
  const video = entry?.video
  const result = status === 'completed' ? entry?.result : null
  const chapters = result?.chapters || []

  const paragraphs = useMemo(() => (result ? buildParagraphs(result.segments) : []), [result])
  const visibleParagraphs = useMemo(() => {
    const q = query.trim().toLowerCase()
    return q ? paragraphs.filter((p) => p.text.toLowerCase().includes(q)) : paragraphs
  }, [paragraphs, query])

  const activeChapterIndex = useMemo(() => {
    let idx = -1
    chapters.forEach((chapter, i) => {
      if (currentTime >= chapter.start) idx = i
    })
    return idx
  }, [chapters, currentTime])

  const seekTo = useCallback((seconds) => {
    playerRef.current?.seekTo(seconds)
    setCurrentTime(seconds)
    if (window.innerWidth < 1024) window.scrollTo({ top: 0, behavior: 'smooth' })
  }, [])

  const handleTimeUpdate = useCallback((t) => setCurrentTime(t), [])

  const handleRetry = async () => {
    setRetrying(true)
    try {
      const fresh = await analyzeVideo(video?.url || youtubeUrl(videoId))
      window.dispatchEvent(new Event(USAGE_CHANGED))
      const next = { id: fresh.id, video: fresh.video, status: fresh.status, result: fresh.result ?? undefined, error: fresh.error }
      await saveEntry(next)
      setEntry(next)
      setPolling(ACTIVE.has(fresh.status))
    } catch (err) {
      setEntry((prev) => ({ ...prev, error: err.message }))
    } finally {
      setRetrying(false)
    }
  }

  /** The server lost this video (e.g. after a redeploy): analyze it again, then resolve. */
  const restoreOnServer = useCallback(async () => {
    await analyzeVideo(video?.url || youtubeUrl(videoId))
    for (let i = 0; i < 60; i += 1) {
      await new Promise((r) => setTimeout(r, 2500))
      const lite = await getVideo(videoId, { includeResult: false })
      if (lite.status === 'completed') return
      if (lite.status === 'failed') throw new Error(lite.error || 'This video could not be analyzed again.')
    }
    throw new Error('This is taking too long. Try again in a minute.')
  }, [video, videoId])

  const copy = async (kind) => {
    try {
      const text = kind === 'brief' ? briefAsMarkdown(video, result) : window.location.href
      await navigator.clipboard.writeText(text)
      setCopied(kind)
      setTimeout(() => setCopied(null), 1800)
    } catch {
      // clipboard unavailable
    }
  }

  if (loadError) {
    return (
      <div className="grain min-h-screen">
        <AppHeader />
        <div className="mx-auto max-w-xl px-5 py-24 text-center">
          <p className="font-display text-3xl text-neutral-100">Couldn't open this video</p>
          <p className="mt-2 text-sm leading-relaxed text-neutral-500">{loadError}</p>
          <Link to="/" className="btn-ghost mt-8">
            <ArrowLeft /> Back to VidMind
          </Link>
        </div>
      </div>
    )
  }

  if (loading || !entry) {
    return (
      <div className="grain min-h-screen">
        <AppHeader />
        <div className="mx-auto max-w-6xl space-y-4 px-5 py-12 sm:px-8">
          <div className="skeleton h-4 w-24" />
          <div className="skeleton h-10 w-2/3" />
          <div className="skeleton mt-8 aspect-video w-full max-w-3xl rounded-3xl" />
        </div>
      </div>
    )
  }

  const meta = [formatDuration(video?.duration), languageName(result?.language)].filter(Boolean)

  return (
    <div className="grain min-h-screen">
      <AppHeader>
        {status === 'completed' && (
          <button type="button" onClick={() => copy('link')} className="btn-quiet">
            {copied === 'link' ? <Check className="h-3.5 w-3.5" /> : <LinkIcon className="h-3.5 w-3.5" />}
            <span className="hidden sm:inline">{copied === 'link' ? 'Link copied' : 'Share'}</span>
          </button>
        )}
        {video?.url && (
          <a href={video.url} target="_blank" rel="noopener noreferrer" className="btn-quiet">
            <span className="hidden sm:inline">YouTube</span>
            <ArrowUpRight className="h-3.5 w-3.5" />
          </a>
        )}
        <button
          type="button"
          onClick={() => setConfirmingRemove(true)}
          className="btn-quiet hover:text-rose-300"
          aria-label="Remove from library"
        >
          <Trash className="h-3.5 w-3.5" />
        </button>
      </AppHeader>

      <div className="pointer-events-none absolute inset-x-0 top-0 h-[28rem] bg-[radial-gradient(ellipse_at_30%_0%,rgba(139,108,255,0.14),transparent_60%)]" />

      <main className="relative mx-auto max-w-6xl px-5 pb-24 pt-8 sm:px-8 sm:pt-10">
        <Link to="/" className="inline-flex items-center gap-1.5 text-xs text-neutral-500 transition hover:text-neutral-200">
          <ArrowLeft className="h-3.5 w-3.5" /> Library
        </Link>

        <div className="mt-5 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 animate-fade-up">
            <div className="flex flex-wrap items-center gap-2 text-xs text-neutral-500">
              <Youtube className="h-3.5 w-3.5" />
              <span>YouTube</span>
              {meta.map((m) => (
                <span key={m} className="flex items-center gap-2">
                  <span className="text-neutral-700">·</span>
                  {m}
                </span>
              ))}
            </div>
            <h1 className="mt-3 max-w-4xl font-display text-4xl leading-[1.05] tracking-tight text-neutral-50 sm:text-5xl">
              {video?.title || 'YouTube video'}
            </h1>
          </div>
          <StatusBadge status={status} className="self-start" />
        </div>

        {ACTIVE.has(status) && (
          <div className="mt-10 max-w-3xl animate-fade-up">
            <ProcessingTimeline progress={entry.progress ?? 5} stage={entry.stage} />
            {pollError && <p className="mt-3 text-sm text-rose-300">{pollError}</p>}
            <p className="mt-4 text-[13px] leading-relaxed text-neutral-500">
              Usually about 30 seconds. You can leave this page; the video will be waiting in your library.
            </p>
          </div>
        )}

        {status === 'failed' && (
          <div className="card mt-10 max-w-3xl animate-fade-up border-rose-400/20 p-7">
            <p className="font-display text-2xl text-neutral-100">Couldn't summarize this video</p>
            <p className="mt-2 text-sm leading-relaxed text-neutral-400">
              {entry.error || 'Something went wrong while analyzing this video.'}
            </p>
            <button type="button" onClick={handleRetry} disabled={retrying} className="btn-primary mt-6">
              <Retry /> {retrying ? 'Retrying…' : 'Try again'}
            </button>
          </div>
        )}

        {result && (
          <div className="mt-10 grid grid-cols-1 gap-8 lg:grid-cols-12">
            {/* Left: player + chapters */}
            <div className="lg:col-span-7">
              <div className="space-y-6 lg:sticky lg:top-24">
                <div className="overflow-hidden rounded-3xl border border-white/[0.08] bg-black shadow-card">
                  <Player ref={playerRef} videoId={videoId} title={video?.title} onTimeUpdate={handleTimeUpdate} />
                </div>

                {chapters.length > 0 && (
                  <section className="card p-5 sm:p-6">
                    <div className="mb-3 flex items-center justify-between">
                      <h2 className="eyebrow">Chapters</h2>
                      <span className="font-mono text-[11px] text-neutral-600">{chapters.length}</span>
                    </div>
                    <ol className="max-h-[22rem] space-y-0.5 overflow-y-auto pr-1">
                      {chapters.map((chapter, idx) => {
                        const active = idx === activeChapterIndex
                        return (
                          <li key={idx}>
                            <button
                              type="button"
                              onClick={() => seekTo(chapter.start)}
                              aria-current={active ? 'true' : undefined}
                              className={`group flex w-full gap-4 rounded-2xl px-3 py-2.5 text-left transition focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 ${
                                active ? 'bg-accent/[0.09]' : 'hover:bg-white/[0.04]'
                              }`}
                            >
                              <span className={`timestamp w-12 shrink-0 pt-px ${active ? '' : 'text-neutral-500 group-hover:text-accent/90'}`}>
                                {formatTimestamp(chapter.start)}
                              </span>
                              <span className="min-w-0">
                                <span className={`block text-sm font-medium ${active ? 'text-white' : 'text-neutral-200'}`}>
                                  {chapter.title}
                                </span>
                                {chapter.summary && (
                                  <span className="mt-0.5 line-clamp-2 block text-[13px] leading-relaxed text-neutral-500">
                                    {chapter.summary}
                                  </span>
                                )}
                              </span>
                            </button>
                          </li>
                        )
                      })}
                    </ol>
                  </section>
                )}
              </div>
            </div>

            {/* Right: tabs */}
            <div className="lg:col-span-5">
              <div role="tablist" aria-label="Video insights" className="mb-5 inline-flex rounded-full border border-white/[0.08] bg-white/[0.02] p-1">
                {TABS.map((t) => (
                  <button
                    key={t.key}
                    role="tab"
                    type="button"
                    aria-selected={tab === t.key}
                    onClick={() => setTab(t.key)}
                    className={`rounded-full px-4 py-1.5 text-sm transition focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 ${
                      tab === t.key ? 'bg-white text-ink-950' : 'text-neutral-400 hover:text-neutral-100'
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>

              {tab === 'brief' && (
                <div role="tabpanel" className="animate-fade-up space-y-8">
                  {result.tldr && (
                    <div className="relative overflow-hidden rounded-3xl border border-gold/20 bg-gradient-to-br from-gold/[0.08] to-transparent p-6">
                      <p className="eyebrow text-gold/80">TL;DR</p>
                      <p className="mt-2 font-display text-[1.6rem] leading-snug text-neutral-50">{result.tldr}</p>
                    </div>
                  )}

                  <section>
                    <div className="mb-3 flex items-center justify-between">
                      <h2 className="eyebrow">Summary</h2>
                      <button type="button" onClick={() => copy('brief')} className="btn-quiet text-xs">
                        {copied === 'brief' ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                        {copied === 'brief' ? 'Copied' : 'Copy brief'}
                      </button>
                    </div>
                    <div className="space-y-4 text-[15px] leading-[1.75] text-neutral-300">
                      {result.summary
                        .split(/\n\s*\n/)
                        .filter(Boolean)
                        .map((para, i) => (
                          <p key={i}>{para}</p>
                        ))}
                    </div>
                  </section>

                  {result.key_points.length > 0 && (
                    <section>
                      <h2 className="eyebrow mb-4">Key points</h2>
                      <ol className="space-y-3">
                        {result.key_points.map((point, idx) => (
                          <li key={idx} className="flex gap-4 rounded-2xl border border-white/[0.06] bg-white/[0.015] p-4">
                            <span className="font-mono text-xs leading-6 text-accent">{String(idx + 1).padStart(2, '0')}</span>
                            <span className="text-sm leading-relaxed text-neutral-200">{point}</span>
                          </li>
                        ))}
                      </ol>
                    </section>
                  )}
                </div>
              )}

              {tab === 'ask' && (
                <div role="tabpanel" className="animate-fade-up">
                  <AskVideo videoId={videoId} chapters={chapters} onSeek={seekTo} onRestore={restoreOnServer} />
                </div>
              )}

              {tab === 'transcript' && (
                <div role="tabpanel" className="animate-fade-up">
                  <div className="relative mb-4">
                    <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-500" />
                    <label htmlFor="transcript-search" className="sr-only">
                      Search transcript
                    </label>
                    <input
                      id="transcript-search"
                      type="text"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      placeholder="Search words in the transcript"
                      className="input pl-11"
                    />
                  </div>
                  {paragraphs.length === 0 ? (
                    <Skeleton />
                  ) : (
                    <div className="max-h-[36rem] space-y-1 overflow-y-auto pr-1">
                      {visibleParagraphs.length === 0 && <p className="px-3 text-sm text-neutral-500">No matches.</p>}
                      {visibleParagraphs.map((p) => {
                        const active = currentTime >= p.start && currentTime < p.end
                        return (
                          <button
                            key={p.start}
                            type="button"
                            onClick={() => seekTo(p.start)}
                            className={`flex w-full gap-4 rounded-2xl px-3 py-3 text-left transition focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 ${
                              active ? 'bg-accent/[0.08]' : 'hover:bg-white/[0.03]'
                            }`}
                          >
                            <span className="timestamp w-12 shrink-0 pt-0.5">{formatTimestamp(p.start)}</span>
                            <span className="text-sm leading-relaxed text-neutral-300">{highlightMatch(p.text, query)}</span>
                          </button>
                        )
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </main>

      {confirmingRemove && (
        <ConfirmDialog
          title="Remove from your library?"
          description="It's only removed from this browser. You can open or analyze the video again any time."
          confirmLabel="Remove"
          onCancel={() => setConfirmingRemove(false)}
          onConfirm={async () => {
            setConfirmingRemove(false)
            await deleteEntries([videoId])
            navigate('/')
          }}
        />
      )}
    </div>
  )
}
