import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { analyzeVideo } from '../services/api.js'
import { saveEntry } from '../services/library.js'
import { USAGE_CHANGED } from './AppHeader.jsx'
import { ArrowRight, Youtube } from './Icons.jsx'

/** Paste a YouTube link, get a brief. */
export default function Omnibox() {
  const navigate = useNavigate()
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    if (!url.trim() || busy) return
    setBusy(true)
    setError(null)
    try {
      const job = await analyzeVideo(url.trim())
      await saveEntry({
        id: job.id,
        video: job.video,
        status: job.status,
        result: job.result ?? undefined,
        error: job.error,
      })
      window.dispatchEvent(new Event(USAGE_CHANGED))
      navigate(`/videos/${job.id}`)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <div className="relative">
      {/* Gradient halo behind the box. */}
      <div className="pointer-events-none absolute -inset-px rounded-[28px] bg-gradient-to-r from-accent-strong/40 via-white/10 to-gold/30 opacity-60 blur-xl" />

      <form
        onSubmit={submit}
        className="relative flex flex-col gap-2 rounded-[28px] border border-white/10 bg-ink-900/90 p-2 shadow-card backdrop-blur-2xl sm:flex-row sm:items-center"
      >
        <label htmlFor="omnibox-url" className="sr-only">
          YouTube link
        </label>
        <div className="flex min-w-0 flex-1 items-center gap-3 pl-4">
          <Youtube className="h-[18px] w-[18px] shrink-0 text-neutral-500" />
          <input
            id="omnibox-url"
            type="text"
            inputMode="url"
            autoComplete="off"
            spellCheck="false"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="Paste a YouTube link"
            className="h-12 min-w-0 flex-1 bg-transparent text-[15px] text-neutral-100 placeholder-neutral-500 focus:outline-none"
          />
        </div>
        <button type="submit" disabled={!url.trim() || busy} className="btn-primary h-12 rounded-[20px] px-6">
          {busy ? 'Starting…' : 'Summarize'}
          {!busy && <ArrowRight />}
        </button>
      </form>

      {error && (
        <p role="alert" className="mt-3 px-4 text-sm text-rose-300">
          {error}
        </p>
      )}
    </div>
  )
}
