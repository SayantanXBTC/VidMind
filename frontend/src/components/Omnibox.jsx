import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { analyzeYoutubeUrl, uploadVideo } from '../services/api.js'
import { ArrowRight, Link as LinkIcon, Upload } from './Icons.jsx'
import { formatFileSize } from '../utils/format.js'

const ACCEPTED = '.mp4,.mov,.avi,.mkv,.webm,video/*'

/** One entry point for both sources: paste a YouTube link, or drop / pick a file. */
export default function Omnibox({ uploadsEnabled = true, onStarted }) {
  const navigate = useNavigate()
  const inputRef = useRef(null)
  const fileRef = useRef(null)
  const [url, setUrl] = useState('')
  const [dragActive, setDragActive] = useState(false)
  const [busy, setBusy] = useState(false)
  const [upload, setUpload] = useState(null) // { name, size, progress }
  const [error, setError] = useState(null)

  const submitUrl = async (e) => {
    e.preventDefault()
    if (!url.trim() || busy) return
    setBusy(true)
    setError(null)
    try {
      const result = await analyzeYoutubeUrl(url.trim())
      onStarted?.()
      navigate(`/videos/${result.id}`)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  const startUpload = async (file) => {
    if (!file || busy) return
    setBusy(true)
    setError(null)
    setUpload({ name: file.name, size: file.size, progress: 0 })
    try {
      const result = await uploadVideo(file, (progress) =>
        setUpload((prev) => (prev ? { ...prev, progress } : prev))
      )
      onStarted?.()
      navigate(`/videos/${result.id}`)
    } catch (err) {
      setError(err.message)
      setUpload(null)
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const onDrop = (e) => {
    e.preventDefault()
    setDragActive(false)
    if (!uploadsEnabled) {
      setError('File uploads are turned off here. Paste a YouTube link instead.')
      return
    }
    startUpload(e.dataTransfer.files?.[0])
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        setDragActive(true)
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setDragActive(false)
      }}
      onDrop={onDrop}
      className="relative"
    >
      {/* Gradient halo behind the box. */}
      <div
        className={`pointer-events-none absolute -inset-px rounded-[28px] bg-gradient-to-r from-accent-strong/40 via-white/10 to-gold/30 opacity-60 blur-xl transition-opacity duration-500 ${
          dragActive ? 'opacity-100' : ''
        }`}
      />

      <div
        className={`relative rounded-[28px] border bg-ink-900/90 p-2 shadow-card backdrop-blur-2xl transition-colors duration-300 ${
          dragActive ? 'border-accent/60' : 'border-white/10'
        }`}
      >
        {upload ? (
          <div className="flex items-center gap-4 px-4 py-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-accent/10 text-accent">
              <Upload className="h-[18px] w-[18px]" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline justify-between gap-3">
                <p className="truncate text-sm text-neutral-100">{upload.name}</p>
                <p className="shrink-0 font-mono text-[11px] tabular-nums text-neutral-500">
                  {upload.progress < 100 ? `${upload.progress}%` : 'Starting analysis…'}
                </p>
              </div>
              <div className="mt-2 h-1 overflow-hidden rounded-full bg-white/[0.07]">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-accent-strong to-accent transition-[width] duration-300"
                  style={{ width: `${upload.progress}%` }}
                />
              </div>
              <p className="mt-1.5 text-[11px] text-neutral-600">{formatFileSize(upload.size)}</p>
            </div>
          </div>
        ) : (
          <form onSubmit={submitUrl} className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <label htmlFor="omnibox-url" className="sr-only">
              YouTube link
            </label>
            <div className="flex min-w-0 flex-1 items-center gap-3 pl-4">
              <LinkIcon className="h-[18px] w-[18px] shrink-0 text-neutral-500" />
              <input
                ref={inputRef}
                id="omnibox-url"
                type="text"
                inputMode="url"
                autoComplete="off"
                spellCheck="false"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder={
                  dragActive
                    ? 'Drop to upload…'
                    : uploadsEnabled
                      ? 'Paste a YouTube link, or drop a video file'
                      : 'Paste a YouTube link'
                }
                className="h-12 min-w-0 flex-1 bg-transparent text-[15px] text-neutral-100 placeholder-neutral-500 focus:outline-none"
              />
            </div>
            <div className="flex gap-2">
              {uploadsEnabled && (
                <button
                  type="button"
                  onClick={() => fileRef.current?.click()}
                  disabled={busy}
                  className="btn-ghost h-12 flex-1 rounded-[20px] sm:flex-none"
                >
                  <Upload />
                  <span>Upload</span>
                </button>
              )}
              <button
                type="submit"
                disabled={!url.trim() || busy}
                className="btn-primary h-12 flex-1 rounded-[20px] px-6 sm:flex-none"
              >
                {busy ? 'Analyzing…' : 'Analyze'}
                {!busy && <ArrowRight />}
              </button>
            </div>
            <input
              ref={fileRef}
              type="file"
              accept={ACCEPTED}
              className="hidden"
              onChange={(e) => startUpload(e.target.files?.[0])}
            />
          </form>
        )}
      </div>

      {error && (
        <p role="alert" className="mt-3 px-4 text-sm text-rose-300">
          {error}
        </p>
      )}
    </div>
  )
}
