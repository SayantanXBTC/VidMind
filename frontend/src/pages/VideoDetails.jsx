import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import AppHeader from '../components/AppHeader.jsx'
import StatusBadge from '../components/StatusBadge.jsx'
import ProcessingTimeline from '../components/ProcessingTimeline.jsx'
import ConfirmDialog from '../components/ConfirmDialog.jsx'
import AskVideo from '../components/AskVideo.jsx'
import SemanticSearch from '../components/SemanticSearch.jsx'
import Player from '../components/Player.jsx'
import {
  ArrowLeft,
  ArrowUpRight,
  Check,
  Copy,
  Film,
  Retry,
  Search,
  Trash,
  Youtube,
} from '../components/Icons.jsx'
import useVideoStatus from '../hooks/useVideoStatus.js'
import { useAuth } from '../auth/AuthProvider.jsx'
import { deleteVideo, getSummary, getTranscript, getVideo, retryVideo } from '../services/api.js'
import { formatDuration, formatTimestamp, videoTitle } from '../utils/format.js'

const TABS = [
  { key: 'brief', label: 'Brief' },
  { key: 'ask', label: 'Ask' },
  { key: 'transcript', label: 'Transcript' },
]

const LANGUAGE_NAMES = typeof Intl.DisplayNames === 'function'
  ? new Intl.DisplayNames(['en'], { type: 'language' })
  : null

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
    if (current.end - current.start >= targetSeconds && /[.!?]$/.test(seg.text.trim())) {
      paragraphs.push(current)
      current = null
    } else if (current.end - current.start >= targetSeconds * 1.6) {
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

function briefAsMarkdown(title, summary) {
  const lines = [`# ${title}`, '']
  if (summary.tldr) lines.push(`> ${summary.tldr}`, '')
  lines.push('## Summary', '', summary.summary, '')
  if (summary.key_points.length) {
    lines.push('## Key points', '', ...summary.key_points.map((p) => `- ${p}`), '')
  }
  if (summary.chapters.length) {
    lines.push('## Chapters', '', ...summary.chapters.map((c) => `- ${formatTimestamp(c.start)} ${c.title}`))
  }
  return lines.join('\n')
}

function BriefSkeleton() {
  return (
    <div className="space-y-4">
      <div className="skeleton h-20 w-full rounded-2xl" />
      <div className="skeleton h-3 w-full" />
      <div className="skeleton h-3 w-11/12" />
      <div className="skeleton h-3 w-9/12" />
      <div className="skeleton mt-6 h-3 w-10/12" />
      <div className="skeleton h-3 w-8/12" />
    </div>
  )
}

export default function VideoDetails() {
  const { videoId } = useParams()
  const navigate = useNavigate()
  const { accessToken, refreshAccount } = useAuth()
  const playerRef = useRef(null)
  const [video, setVideo] = useState(null)
  const [loadError, setLoadError] = useState(null)
  const [transcript, setTranscript] = useState(null)
  const [transcriptError, setTranscriptError] = useState(null)
  const [summary, setSummary] = useState(null)
  const [summaryError, setSummaryError] = useState(null)
  const [tab, setTab] = useState('brief')
  const [transcriptQuery, setTranscriptQuery] = useState('')
  const [smartSearch, setSmartSearch] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [retryError, setRetryError] = useState(null)
  const [justRetried, setJustRetried] = useState(false)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    getVideo(videoId)
      .then(setVideo)
      .catch((err) => setLoadError(err.message))
  }, [videoId])

  const isActive =
    justRetried || (video && (video.status === 'processing' || video.status === 'uploaded'))
  const { status, progress, error: statusError } = useVideoStatus(videoId, {
    active: Boolean(isActive),
    initialStatus: justRetried ? 'processing' : video?.status,
    initialProgress: justRetried ? 5 : video?.processing_progress,
  })

  const effectiveStatus = status || video?.status

  useEffect(() => {
    if (effectiveStatus === 'failed') {
      setJustRetried(false)
      getVideo(videoId).then(setVideo).catch(() => {})
    }
    if (effectiveStatus !== 'completed') return
    setJustRetried(false)
    getVideo(videoId).then(setVideo).catch(() => {})
    getTranscript(videoId)
      .then(setTranscript)
      .catch((err) => setTranscriptError(err.message))
    getSummary(videoId)
      .then(setSummary)
      .catch((err) => setSummaryError(err.message))
  }, [effectiveStatus, videoId])

  const paragraphs = useMemo(
    () => (transcript ? buildParagraphs(transcript.segments) : []),
    [transcript]
  )

  const filteredParagraphs = useMemo(() => {
    const q = transcriptQuery.trim().toLowerCase()
    if (!q) return paragraphs
    return paragraphs.filter((p) => p.text.toLowerCase().includes(q))
  }, [paragraphs, transcriptQuery])

  const activeChapterIndex = useMemo(() => {
    if (!summary?.chapters?.length) return -1
    let idx = -1
    summary.chapters.forEach((chapter, i) => {
      if (currentTime >= chapter.start) idx = i
    })
    return idx
  }, [summary, currentTime])

  const seekTo = useCallback((seconds) => {
    playerRef.current?.seekTo(seconds)
    setCurrentTime(seconds)
    // On small screens the player scrolls away; bring it back into view.
    if (window.innerWidth < 1024) window.scrollTo({ top: 0, behavior: 'smooth' })
  }, [])

  const handleTimeUpdate = useCallback((t) => setCurrentTime(t), [])

  const handleDelete = async () => {
    try {
      await deleteVideo(videoId)
      refreshAccount()
      navigate('/')
    } catch (err) {
      setLoadError(err.message)
    }
  }

  const handleRetry = async () => {
    setRetrying(true)
    setRetryError(null)
    try {
      await retryVideo(videoId)
      setJustRetried(true)
    } catch (err) {
      setRetryError(err.message)
    } finally {
      setRetrying(false)
    }
  }

  const handleCopy = async () => {
    if (!summary) return
    try {
      await navigator.clipboard.writeText(briefAsMarkdown(videoTitle(video), summary))
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    } catch {
      // clipboard unavailable (e.g. insecure context) — nothing useful to show
    }
  }

  if (loadError) {
    return (
      <div className="grain min-h-screen">
        <AppHeader />
        <div className="mx-auto max-w-xl px-5 py-24 text-center">
          <p className="font-display text-3xl text-neutral-100">Couldn't open this video</p>
          <p className="mt-2 text-sm text-neutral-500">{loadError}</p>
          <Link to="/" className="btn-ghost mt-8">
            <ArrowLeft /> Back to library
          </Link>
        </div>
      </div>
    )
  }

  if (!video) {
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

  const isYoutube = video.source_type === 'youtube'
  const title = videoTitle(video)
  const isCompleted = effectiveStatus === 'completed'
  const isFailed = effectiveStatus === 'failed'
  const isProcessing = !isCompleted && !isFailed
  const chapters = summary?.chapters || []

  const meta = [
    formatDuration(video.duration),
    languageName(video.language),
    video.ingestion_method === 'caption'
      ? 'From YouTube captions'
      : video.ingestion_method === 'whisper'
        ? 'Transcribed locally'
        : null,
  ].filter(Boolean)

  return (
    <div className="grain min-h-screen">
      <AppHeader>
        {isYoutube && video.source_url && (
          <a href={video.source_url} target="_blank" rel="noopener noreferrer" className="btn-quiet">
            <span className="hidden sm:inline">Open on YouTube</span>
            <ArrowUpRight className="h-3.5 w-3.5" />
          </a>
        )}
        <button
          type="button"
          onClick={() => setConfirmingDelete(true)}
          className="btn-quiet hover:text-rose-300"
          aria-label="Delete video"
        >
          <Trash className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">Delete</span>
        </button>
      </AppHeader>

      <div className="pointer-events-none absolute inset-x-0 top-0 -z-0 h-[28rem] bg-[radial-gradient(ellipse_at_30%_0%,rgba(139,108,255,0.14),transparent_60%)]" />

      <main className="relative mx-auto max-w-6xl px-5 pb-24 pt-8 sm:px-8 sm:pt-10">
        <Link
          to="/"
          className="inline-flex items-center gap-1.5 text-xs text-neutral-500 transition hover:text-neutral-200"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> Library
        </Link>

        {/* Title block */}
        <div className="mt-5 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 animate-fade-up">
            <div className="flex flex-wrap items-center gap-2 text-xs text-neutral-500">
              {isYoutube ? <Youtube className="h-3.5 w-3.5" /> : <Film className="h-3.5 w-3.5" />}
              <span>{isYoutube ? 'YouTube' : 'Upload'}</span>
              {meta.map((m) => (
                <span key={m} className="flex items-center gap-2">
                  <span className="text-neutral-700">·</span>
                  {m}
                </span>
              ))}
            </div>
            <h1 className="mt-3 max-w-4xl font-display text-4xl leading-[1.05] tracking-tight text-neutral-50 sm:text-5xl">
              {title}
            </h1>
          </div>
          <StatusBadge status={effectiveStatus} className="self-start" />
        </div>

        {isProcessing && (
          <div className="mt-10 max-w-3xl animate-fade-up">
            <ProcessingTimeline progress={progress || 5} sourceType={video.source_type} />
            {statusError && <p className="mt-3 text-sm text-rose-300">{statusError}</p>}
            <p className="mt-4 text-[13px] leading-relaxed text-neutral-500">
              You can leave this page — analysis continues in the background and the video will be
              waiting in your library.
            </p>
          </div>
        )}

        {isFailed && (
          <div className="card mt-10 max-w-3xl animate-fade-up border-rose-400/20 p-7">
            <p className="font-display text-2xl text-neutral-100">Analysis didn't finish</p>
            <p className="mt-2 text-sm leading-relaxed text-neutral-400">
              {video.error_message || 'Something went wrong while processing this video.'}
            </p>
            {retryError && <p className="mt-3 text-sm text-rose-300">{retryError}</p>}
            <button
              type="button"
              onClick={handleRetry}
              disabled={retrying}
              className="btn-primary mt-6"
            >
              <Retry /> {retrying ? 'Retrying…' : 'Try again'}
            </button>
          </div>
        )}

        {isCompleted && (
          <div className="mt-10 grid grid-cols-1 gap-8 lg:grid-cols-12">
            {/* Left: player + chapters */}
            <div className="lg:col-span-7">
              <div className="space-y-6 lg:sticky lg:top-24">
                <div className="overflow-hidden rounded-3xl border border-white/[0.08] bg-black shadow-card">
                  <Player ref={playerRef} video={video} accessToken={accessToken} onTimeUpdate={handleTimeUpdate} />
                </div>

                {chapters.length > 0 && (
                  <section className="card p-5 sm:p-6">
                    <div className="mb-3 flex items-center justify-between">
                      <h2 className="eyebrow">Chapters</h2>
                      <span className="font-mono text-[11px] text-neutral-600">
                        {chapters.length}
                      </span>
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
                              <span
                                className={`timestamp w-12 shrink-0 pt-px ${active ? '' : 'text-neutral-500 group-hover:text-accent/90'}`}
                              >
                                {formatTimestamp(chapter.start)}
                              </span>
                              <span className="min-w-0">
                                <span
                                  className={`block text-sm font-medium ${active ? 'text-white' : 'text-neutral-200'}`}
                                >
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
              <div
                role="tablist"
                aria-label="Video insights"
                className="mb-5 inline-flex rounded-full border border-white/[0.08] bg-white/[0.02] p-1"
              >
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
                  {summaryError && <p className="text-sm text-rose-300">{summaryError}</p>}
                  {!summary && !summaryError && <BriefSkeleton />}

                  {summary && (
                    <>
                      {summary.tldr && (
                        <div className="relative overflow-hidden rounded-3xl border border-gold/20 bg-gradient-to-br from-gold/[0.08] to-transparent p-6">
                          <p className="eyebrow text-gold/80">TL;DR</p>
                          <p className="mt-2 font-display text-[1.6rem] leading-snug text-neutral-50">
                            {summary.tldr}
                          </p>
                        </div>
                      )}

                      <section>
                        <div className="mb-3 flex items-center justify-between">
                          <h2 className="eyebrow">Summary</h2>
                          <button type="button" onClick={handleCopy} className="btn-quiet text-xs">
                            {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                            {copied ? 'Copied' : 'Copy brief'}
                          </button>
                        </div>
                        <div className="space-y-4 text-[15px] leading-[1.75] text-neutral-300">
                          {summary.summary
                            .split(/\n\s*\n/)
                            .filter(Boolean)
                            .map((para, i) => (
                              <p key={i}>{para}</p>
                            ))}
                        </div>
                      </section>

                      {summary.key_points.length > 0 && (
                        <section>
                          <h2 className="eyebrow mb-4">Key points</h2>
                          <ol className="space-y-3">
                            {summary.key_points.map((point, idx) => (
                              <li
                                key={idx}
                                className="flex gap-4 rounded-2xl border border-white/[0.06] bg-white/[0.015] p-4"
                              >
                                <span className="font-mono text-xs leading-6 text-accent">
                                  {String(idx + 1).padStart(2, '0')}
                                </span>
                                <span className="text-sm leading-relaxed text-neutral-200">{point}</span>
                              </li>
                            ))}
                          </ol>
                        </section>
                      )}
                    </>
                  )}
                </div>
              )}

              {tab === 'ask' && (
                <div role="tabpanel" className="animate-fade-up">
                  <AskVideo
                    videoId={video.id}
                    embeddingStatus={video.embedding_status}
                    chapters={chapters}
                    onSeek={seekTo}
                  />
                </div>
              )}

              {tab === 'transcript' && (
                <div role="tabpanel" className="animate-fade-up">
                  <div className="mb-4 flex items-center justify-between gap-3">
                    <h2 className="eyebrow">
                      {smartSearch ? 'Smart search' : `Transcript · ${paragraphs.length} sections`}
                    </h2>
                    <button
                      type="button"
                      onClick={() => setSmartSearch((v) => !v)}
                      className="btn-quiet text-xs"
                    >
                      {smartSearch ? 'Show transcript' : 'Search by meaning'}
                    </button>
                  </div>

                  {smartSearch ? (
                    <SemanticSearch
                      videoId={video.id}
                      embeddingStatus={video.embedding_status}
                      onSeek={seekTo}
                    />
                  ) : (
                    <>
                      <div className="relative mb-4">
                        <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-500" />
                        <label htmlFor="transcript-search" className="sr-only">
                          Search transcript
                        </label>
                        <input
                          id="transcript-search"
                          type="text"
                          value={transcriptQuery}
                          onChange={(e) => setTranscriptQuery(e.target.value)}
                          placeholder="Search words in the transcript"
                          className="input pl-11"
                        />
                      </div>

                      {transcriptError && <p className="text-sm text-rose-300">{transcriptError}</p>}
                      {!transcript && !transcriptError && <BriefSkeleton />}

                      {transcript && (
                        <div className="max-h-[36rem] space-y-1 overflow-y-auto pr-1">
                          {filteredParagraphs.length === 0 && (
                            <p className="px-3 text-sm text-neutral-500">No matches.</p>
                          )}
                          {filteredParagraphs.map((p) => {
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
                                <span className="timestamp w-12 shrink-0 pt-0.5">
                                  {formatTimestamp(p.start)}
                                </span>
                                <span className="text-sm leading-relaxed text-neutral-300">
                                  {highlightMatch(p.text, transcriptQuery)}
                                </span>
                              </button>
                            )
                          })}
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </main>

      {confirmingDelete && (
        <ConfirmDialog
          title="Delete this video?"
          description="Its transcript, summary, chapters and search index will be removed too."
          confirmLabel="Delete"
          onCancel={() => setConfirmingDelete(false)}
          onConfirm={() => {
            setConfirmingDelete(false)
            handleDelete()
          }}
        />
      )}
    </div>
  )
}
