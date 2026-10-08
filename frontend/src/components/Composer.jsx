import { forwardRef, useImperativeHandle, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { analyzeVideo, uploadVideo } from '../services/api.js'
import { saveEntry } from '../services/library.js'
import { rememberFile } from '../services/localFiles.js'
import { USAGE_CHANGED } from './AppHeader.jsx'
import { ArrowRight, FileVideo, Upload, Youtube } from './Icons.jsx'

const ACCEPT = '.mp4,.m4v,.mov,.webm,.mkv,.avi,video/*'
const VIDEO_EXT = /\.(mp4|m4v|mov|webm|mkv|avi)$/i

function formatMb(bytes) {
  return `${(bytes / (1024 * 1024)).toFixed(bytes < 10 * 1024 * 1024 ? 1 : 0)} MB`
}

async function remember(job) {
  await saveEntry({ id: job.id, video: job.video, status: job.status, result: job.result ?? undefined, error: job.error })
  window.dispatchEvent(new Event(USAGE_CHANGED))
}

/**
 * The main input: paste a YouTube link, or upload a video file. Exposes
 * upload(file) so the page can accept files dropped anywhere on it.
 */
const Composer = forwardRef(function Composer({ uploadsEnabled = true, maxUploadMb }, ref) {
  const navigate = useNavigate()
  const fileRef = useRef(null)
  const [mode, setMode] = useState('link')
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [upload, setUpload] = useState(null) // { name, size, progress }
  const [dragOver, setDragOver] = useState(false)
  const [error, setError] = useState(null)

  const submitLink = async (e) => {
    e.preventDefault()
    if (!url.trim() || busy) return
    setBusy(true)
    setError(null)
    try {
      const job = await analyzeVideo(url.trim())
      await remember(job)
      navigate(`/videos/${job.id}`)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  const startUpload = async (file) => {
    if (!file || busy) return
    setMode('upload')
    setError(null)
    if (!VIDEO_EXT.test(file.name)) {
      setError('Choose a video file: MP4, MOV, M4V, WEBM, MKV or AVI.')
      return
    }
    if (maxUploadMb && file.size > maxUploadMb * 1024 * 1024) {
      setError(`That file is ${formatMb(file.size)}. Videos can be at most ${maxUploadMb} MB.`)
      return
    }
    setBusy(true)
    setUpload({ name: file.name, size: file.size, progress: 0 })
    try {
      const job = await uploadVideo(file, (progress) => setUpload((prev) => prev && { ...prev, progress }))
      rememberFile(job.id, file) // lets the brief page play it from this computer
      await remember(job)
      navigate(`/videos/${job.id}`)
    } catch (err) {
      setError(err.message)
      setUpload(null)
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  useImperativeHandle(ref, () => ({ upload: startUpload }))

  const tabs = [
    { key: 'link', label: 'YouTube link', icon: Youtube },
    ...(uploadsEnabled ? [{ key: 'upload', label: 'Upload video', icon: Upload }] : []),
  ]

  return (
    <div className="relative">
      {/* Ambient halo */}
      <div className="pointer-events-none absolute -inset-6 rounded-[3rem] bg-[radial-gradient(closest-side,rgba(139,108,255,0.35),transparent)] opacity-70 blur-2xl" />

      <div className="glow-border relative rounded-[2rem]">
        <div className="rounded-[2rem] bg-ink-900/90 p-2.5 backdrop-blur-2xl">
          {tabs.length > 1 && (
            <div role="tablist" aria-label="Video source" className="flex gap-1 p-1">
              {tabs.map(({ key, label, icon: Icon }) => (
                <button
                  key={key}
                  role="tab"
                  type="button"
                  aria-selected={mode === key}
                  disabled={busy}
                  onClick={() => {
                    setMode(key)
                    setError(null)
                  }}
                  className={`inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-[13px] transition focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 ${
                    mode === key ? 'bg-white/[0.09] text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]' : 'text-neutral-500 hover:text-neutral-200'
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {label}
                </button>
              ))}
            </div>
          )}

          {mode === 'link' ? (
            <form onSubmit={submitLink} className="flex flex-col gap-2 p-1 sm:flex-row sm:items-center">
              <label htmlFor="composer-url" className="sr-only">
                YouTube link
              </label>
              <div className="flex min-w-0 flex-1 items-center gap-3 pl-4">
                <Youtube className="h-[18px] w-[18px] shrink-0 text-neutral-500" />
                <input
                  id="composer-url"
                  type="text"
                  inputMode="url"
                  autoComplete="off"
                  spellCheck="false"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="Paste a YouTube link"
                  className="h-14 min-w-0 flex-1 bg-transparent text-base text-neutral-100 placeholder-neutral-500 focus:outline-none"
                />
              </div>
              <button type="submit" disabled={!url.trim() || busy} className="btn-primary h-12 rounded-[1.25rem] px-7">
                {busy ? 'Starting…' : 'Summarize'}
                {!busy && <ArrowRight />}
              </button>
            </form>
          ) : upload ? (
            <div className="flex items-center gap-4 p-4">
              <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-accent/10 text-accent">
                <FileVideo className="h-5 w-5" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-3">
                  <p className="truncate text-sm text-neutral-100">{upload.name}</p>
                  <p className="shrink-0 font-mono text-[11px] tabular-nums text-neutral-500">
                    {upload.progress < 100 ? `${upload.progress}%` : 'Starting analysis…'}
                  </p>
                </div>
                <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-white/[0.07]">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-accent-strong via-accent to-aqua transition-[width] duration-300"
                    style={{ width: `${upload.progress}%` }}
                  />
                </div>
                <p className="mt-1.5 text-[11px] text-neutral-600">{formatMb(upload.size)} · uploading</p>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              onDragOver={(e) => {
                e.preventDefault()
                setDragOver(true)
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault()
                e.stopPropagation()
                setDragOver(false)
                startUpload(e.dataTransfer.files?.[0])
              }}
              className={`group m-1 flex w-[calc(100%-0.5rem)] flex-col items-center justify-center gap-3 rounded-[1.5rem] border border-dashed px-6 py-9 text-center transition focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 ${
                dragOver ? 'border-accent/70 bg-accent/[0.08]' : 'border-white/15 hover:border-accent/40 hover:bg-white/[0.02]'
              }`}
            >
              <span className="flex h-14 w-14 items-center justify-center rounded-2xl border border-white/10 bg-gradient-to-b from-white/[0.08] to-transparent text-accent transition group-hover:scale-105">
                <Upload className="h-6 w-6" />
              </span>
              <span className="text-[15px] font-medium text-neutral-100">Drop a video here, or click to choose</span>
              <span className="text-xs text-neutral-500">
                MP4, MOV, WEBM, MKV or AVI{maxUploadMb ? ` · up to ${maxUploadMb} MB` : ''} · the file is deleted after it's transcribed
              </span>
            </button>
          )}
          <input
            ref={fileRef}
            type="file"
            accept={ACCEPT}
            className="hidden"
            onChange={(e) => startUpload(e.target.files?.[0])}
          />
        </div>
      </div>

      {error && (
        <p role="alert" className="mt-4 px-4 text-center text-sm text-rose-300">
          {error}
        </p>
      )}
    </div>
  )
})

export default Composer
