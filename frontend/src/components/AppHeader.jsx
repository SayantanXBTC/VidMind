import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthProvider.jsx'

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

function QuotaChip({ account }) {
  if (!account?.daily_limit) return null
  const left = Math.max(0, account.daily_limit - account.used_today)
  return (
    <span
      className={`hidden items-center gap-2 rounded-full border px-3 py-1.5 text-[11px] sm:inline-flex ${
        left === 0 ? 'border-rose-400/30 text-rose-300' : 'border-white/[0.08] text-neutral-400'
      }`}
      title="Videos you can still analyze in the next 24 hours"
    >
      <span className={`h-1.5 w-1.5 rounded-full ${left === 0 ? 'bg-rose-400' : 'bg-emerald-400'}`} />
      {left} of {account.daily_limit} left today
    </span>
  )
}

function UserMenu() {
  const { user, signOut } = useAuth()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    const close = (e) => {
      if (!ref.current?.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  const email = user?.email || 'Account'
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Account menu"
        className="flex h-9 w-9 items-center justify-center rounded-full border border-white/10 bg-gradient-to-b from-accent/25 to-accent-strong/10 text-sm font-medium uppercase text-neutral-100 transition hover:border-white/25 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
      >
        {email[0]}
      </button>
      {open && (
        <div role="menu" className="card absolute right-0 top-11 w-60 animate-fade-up p-2">
          <p className="truncate px-3 py-2 text-xs text-neutral-500">{email}</p>
          <button
            type="button"
            role="menuitem"
            onClick={signOut}
            className="w-full rounded-xl px-3 py-2 text-left text-sm text-neutral-200 transition hover:bg-white/[0.06]"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  )
}

export default function AppHeader({ children }) {
  const { authEnabled, signedIn, account } = useAuth()
  return (
    <header className="sticky top-0 z-40 border-b border-white/[0.06] bg-ink-950/70 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-5 sm:px-8">
        <Logo />
        <div className="flex items-center gap-2">
          {children}
          {authEnabled && signedIn && (
            <>
              <QuotaChip account={account} />
              <UserMenu />
            </>
          )}
        </div>
      </div>
    </header>
  )
}
