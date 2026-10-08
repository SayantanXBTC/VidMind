import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getUsage } from '../services/api.js'

export function Logo() {
  return (
    <Link
      to="/"
      className="group flex items-center gap-2.5 rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
    >
      <span className="relative flex h-8 w-8 items-center justify-center rounded-[10px] border border-white/10 bg-gradient-to-b from-white/[0.08] to-white/[0.02] shadow-card">
        <svg viewBox="0 0 32 32" className="h-[18px] w-[18px]" aria-hidden="true">
          <path
            d="M9 10l7 13 7-13"
            fill="none"
            stroke="url(#logo-grad)"
            strokeWidth="2.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <defs>
            <linearGradient id="logo-grad" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor="#ffffff" />
              <stop offset="1" stopColor="#B9A6FF" />
            </linearGradient>
          </defs>
        </svg>
      </span>
      <span className="text-[15px] font-semibold tracking-tight text-neutral-100">VidMind</span>
    </Link>
  )
}

export const USAGE_CHANGED = 'vidmind:usage-changed'

/** "3 of 5 new videos left today" — refreshed whenever a new analysis starts. */
function UsageChip() {
  const [usage, setUsage] = useState(null)

  useEffect(() => {
    let cancelled = false
    const load = () =>
      getUsage()
        .then((u) => !cancelled && setUsage(u))
        .catch(() => {})
    load()
    window.addEventListener(USAGE_CHANGED, load)
    return () => {
      cancelled = true
      window.removeEventListener(USAGE_CHANGED, load)
    }
  }, [])

  if (!usage?.analyses_per_day) return null
  const left = Math.max(0, usage.analyses_per_day - usage.analyses_today)
  return (
    <span
      className={`hidden items-center gap-2 rounded-full border px-3 py-1.5 text-[11px] sm:inline-flex ${
        left === 0 ? 'border-rose-400/30 text-rose-300' : 'border-white/[0.08] text-neutral-400'
      }`}
      title="New videos you can analyze in the next 24 hours. Videos someone already analyzed are free."
    >
      <span className={`h-1.5 w-1.5 rounded-full ${left === 0 ? 'bg-rose-400' : 'bg-emerald-400'}`} />
      {left} of {usage.analyses_per_day} new videos left today
    </span>
  )
}

export default function AppHeader({ children }) {
  return (
    <header className="sticky top-0 z-40 border-b border-white/[0.06] bg-ink-950/70 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-5 sm:px-8">
        <Logo />
        <div className="flex items-center gap-2">
          {children}
          <UsageChip />
        </div>
      </div>
    </header>
  )
}
