import { useEffect, useRef, useState } from 'react'
import { askVideo } from '../services/api.js'
import { ArrowRight, Sparkle } from './Icons.jsx'
import { formatTimestamp } from '../utils/format.js'

function suggestionsFor(chapters) {
  const base = ['What are the main takeaways?', 'What is the conclusion?']
  const fromChapters = (chapters || [])
    .slice(1, 3)
    .map((c) => `What does it say about ${c.title.replace(/[.…]+$/, '')}?`)
  return [...base, ...fromChapters].slice(0, 4)
}

export default function AskVideo({ videoId, chapters, onSeek, onRestore }) {
  const [question, setQuestion] = useState('')
  const [thread, setThread] = useState([]) // [{ id, question, answer?, sources?, error?, loading }]
  const endRef = useRef(null)
  const loading = thread.some((t) => t.loading)

  useEffect(() => {
    if (thread.length === 0) return
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [thread])

  const ask = async (text) => {
    const q = text.trim()
    if (!q || loading) return
    const id = Date.now()
    setQuestion('')
    setThread((prev) => [...prev, { id, question: q, loading: true }])
    try {
      let data
      try {
        data = await askVideo(videoId, q)
      } catch (err) {
        if (err.status !== 409 || !onRestore) throw err
        // The server no longer has this video (e.g. after a redeploy):
        // analyze it again, then ask.
        setThread((prev) => prev.map((t) => (t.id === id ? { ...t, restoring: true } : t)))
        await onRestore()
        data = await askVideo(videoId, q)
      }
      setThread((prev) => prev.map((t) => (t.id === id ? { ...t, ...data, loading: false, restoring: false } : t)))
    } catch (err) {
      setThread((prev) =>
        prev.map((t) => (t.id === id ? { ...t, error: err.message, loading: false } : t))
      )
    }
  }

  return (
    <div>
      {thread.length === 0 && (
        <div className="mb-6">
          <div className="flex items-center gap-2 text-neutral-300">
            <Sparkle className="h-4 w-4 text-accent" />
            <p className="text-sm">Ask anything about this video.</p>
          </div>
          <p className="mt-1 text-[13px] text-neutral-500">
            Answers come only from what's said in the video, with timestamps to check them.
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            {suggestionsFor(chapters).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => ask(s)}
                className="rounded-full border border-white/10 bg-white/[0.02] px-3.5 py-1.5 text-left text-[13px] text-neutral-300 transition hover:border-accent/40 hover:bg-accent/[0.06] hover:text-neutral-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-6">
        {thread.map((t) => (
          <div key={t.id} className="animate-fade-up space-y-3">
            <div className="flex justify-end">
              <p className="max-w-[85%] rounded-2xl rounded-br-md bg-white/[0.07] px-4 py-2.5 text-sm text-neutral-100">
                {t.question}
              </p>
            </div>

            <div className="flex gap-3">
              <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-accent/30 bg-accent/10">
                <Sparkle className="h-3.5 w-3.5 text-accent" />
              </span>
              <div className="min-w-0 flex-1">
                {t.loading ? (
                  <div className="space-y-2 pt-1.5">
                    {t.restoring && (
                      <p className="text-xs text-neutral-500">Refreshing this video on the server first…</p>
                    )}
                    <div className="skeleton h-3 w-11/12" />
                    <div className="skeleton h-3 w-8/12" />
                  </div>
                ) : t.error ? (
                  <p className="pt-1 text-sm text-rose-300">{t.error}</p>
                ) : (
                  <>
                    <p className="whitespace-pre-line pt-0.5 text-[15px] leading-relaxed text-neutral-200">
                      {t.answer}
                    </p>
                    {t.sources?.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {t.sources.map((source, idx) => (
                          <button
                            key={idx}
                            type="button"
                            onClick={() => onSeek(source.start)}
                            title={source.text}
                            className="group inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.02] py-1 pl-1 pr-3 text-xs text-neutral-400 transition hover:border-accent/40 hover:text-neutral-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
                          >
                            <span className="rounded-full bg-accent/15 px-2 py-0.5 font-mono text-[11px] text-accent">
                              {formatTimestamp(source.start)}
                            </span>
                            <span className="max-w-[14rem] truncate">{source.text}</span>
                          </button>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          </div>
        ))}
        <div ref={endRef} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          ask(question)
        }}
        className="sticky bottom-0 mt-6 flex items-center gap-2 rounded-full border border-white/10 bg-ink-900/95 p-1.5 pl-5 backdrop-blur-xl focus-within:border-accent/40 focus-within:ring-4 focus-within:ring-accent/10"
      >
        <label htmlFor="ask-video-input" className="sr-only">
          Ask a question about this video
        </label>
        <input
          id="ask-video-input"
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question…"
          className="min-w-0 flex-1 bg-transparent text-sm text-neutral-100 placeholder-neutral-500 focus:outline-none"
        />
        <button
          type="submit"
          disabled={!question.trim() || loading}
          aria-label="Ask"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white text-ink-950 transition hover:bg-neutral-200 disabled:bg-white/10 disabled:text-neutral-500"
        >
          <ArrowRight />
        </button>
      </form>
    </div>
  )
}
