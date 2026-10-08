import { useState } from 'react'
import { searchVideo } from '../services/api.js'
import { Sparkle } from './Icons.jsx'
import { formatTimestamp } from '../utils/format.js'

/** Meaning-based search ("where do they talk about pricing?") over the video's index. */
export default function SemanticSearch({ videoId, embeddingStatus, onSeek }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  if (embeddingStatus !== 'completed') {
    return (
      <p className="text-sm text-neutral-500">
        {embeddingStatus === 'failed'
          ? "Smart search isn't available for this video."
          : 'Preparing the search index…'}
      </p>
    )
  }

  const handleSearch = async (e) => {
    e.preventDefault()
    if (!query.trim()) return
    setLoading(true)
    setError(null)
    try {
      const data = await searchVideo(videoId, query.trim())
      setResults(data.results)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <form onSubmit={handleSearch} className="relative">
        <Sparkle className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-accent" />
        <label htmlFor="semantic-search-input" className="sr-only">
          Find a moment by meaning
        </label>
        <input
          id="semantic-search-input"
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Find a moment by meaning, e.g. “the main argument”"
          className="input pl-11 pr-24"
        />
        <button
          type="submit"
          disabled={!query.trim() || loading}
          className="btn-primary absolute right-1.5 top-1/2 -translate-y-1/2 px-4 py-1.5 text-xs"
        >
          {loading ? 'Finding…' : 'Find'}
        </button>
      </form>

      {error && <p className="mt-3 text-sm text-rose-300">{error}</p>}

      {results && results.length === 0 && (
        <p className="mt-4 text-sm text-neutral-500">No matching moment found.</p>
      )}

      {results && results.length > 0 && (
        <ul className="mt-4 space-y-1">
          {results.map((result, idx) => (
            <li key={idx}>
              <button
                type="button"
                onClick={() => onSeek(result.start)}
                className="flex w-full gap-4 rounded-2xl px-3 py-2.5 text-left transition hover:bg-white/[0.04] focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
              >
                <span className="timestamp shrink-0 pt-0.5">{formatTimestamp(result.start)}</span>
                <span className="line-clamp-3 text-sm leading-relaxed text-neutral-300">
                  {result.text}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
