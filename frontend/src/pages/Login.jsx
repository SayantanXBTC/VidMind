import { useState } from 'react'
import { Logo } from '../components/AppHeader.jsx'
import { ArrowRight, Chapters, Chat, Check } from '../components/Icons.jsx'
import { supabase } from '../services/supabase.js'

// Google sign-in needs an OAuth client configured in Supabase first.
const GOOGLE_ENABLED = import.meta.env.VITE_ENABLE_GOOGLE_AUTH === 'true'

function GoogleMark() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden="true">
      <path fill="#EA4335" d="M12 10.2v3.9h5.5c-.24 1.4-1.7 4.1-5.5 4.1-3.3 0-6-2.7-6-6.1S8.7 6 12 6c1.9 0 3.1.8 3.8 1.5l2.6-2.5C16.8 3.5 14.6 2.5 12 2.5 6.8 2.5 2.6 6.7 2.6 12s4.2 9.5 9.4 9.5c5.4 0 9-3.8 9-9.2 0-.6-.1-1.1-.2-1.6H12z" />
    </svg>
  )
}

export default function Login() {
  const [email, setEmail] = useState('')
  const [sending, setSending] = useState(false)
  const [sentTo, setSentTo] = useState(null)
  const [error, setError] = useState(null)

  const redirectTo = window.location.href

  const sendLink = async (e) => {
    e.preventDefault()
    if (!email.trim() || sending) return
    setSending(true)
    setError(null)
    const { error: err } = await supabase.auth.signInWithOtp({
      email: email.trim(),
      options: { emailRedirectTo: redirectTo },
    })
    setSending(false)
    if (err) setError(err.message)
    else setSentTo(email.trim())
  }

  const signInWithGoogle = async () => {
    setError(null)
    const { error: err } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo },
    })
    if (err) setError(err.message)
  }

  return (
    <div className="grain relative flex min-h-screen flex-col">
      <div className="bg-grid pointer-events-none absolute inset-0" />
      <div className="pointer-events-none absolute left-1/2 top-[-14rem] h-[34rem] w-[56rem] -translate-x-1/2 rounded-full bg-[radial-gradient(closest-side,rgba(139,108,255,0.22),transparent)]" />

      <header className="relative mx-auto flex h-16 w-full max-w-6xl items-center px-5 sm:px-8">
        <Logo />
      </header>

      <main className="relative mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-5 pb-24">
        <h1 className="animate-fade-up text-center font-display text-5xl leading-[1] tracking-tight text-neutral-50 sm:text-6xl">
          Watch less.
          <br />
          <span className="text-gradient italic">Understand more.</span>
        </h1>
        <p
          className="mx-auto mt-5 max-w-sm animate-fade-up text-center text-[15px] leading-relaxed text-neutral-400"
          style={{ animationDelay: '80ms' }}
        >
          Sign in to turn long videos into briefs, chapters and answers.
        </p>

        <div className="card mt-10 animate-fade-up p-6 sm:p-7" style={{ animationDelay: '140ms' }}>
          {sentTo ? (
            <div className="text-center">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-400/10 text-emerald-300">
                <Check className="h-5 w-5" strokeWidth={2.2} />
              </div>
              <p className="mt-5 font-display text-2xl text-neutral-50">Check your inbox</p>
              <p className="mt-2 text-sm leading-relaxed text-neutral-400">
                We sent a sign-in link to <span className="text-neutral-200">{sentTo}</span>. Open it on
                this device to continue.
              </p>
              <button type="button" onClick={() => setSentTo(null)} className="btn-quiet mt-5 text-xs">
                Use a different email
              </button>
            </div>
          ) : (
            <>
              {GOOGLE_ENABLED && (
                <>
                  <button type="button" onClick={signInWithGoogle} className="btn-primary w-full py-3">
                    <GoogleMark />
                    Continue with Google
                  </button>
                  <div className="my-5 flex items-center gap-3 text-[11px] uppercase tracking-[0.18em] text-neutral-600">
                    <span className="h-px flex-1 bg-white/10" />
                    or
                    <span className="h-px flex-1 bg-white/10" />
                  </div>
                </>
              )}

              <form onSubmit={sendLink} className="space-y-3">
                <label htmlFor="login-email" className="eyebrow block">
                  Email
                </label>
                <input
                  id="login-email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="input"
                />
                <button
                  type="submit"
                  disabled={!email.trim() || sending}
                  className={`${GOOGLE_ENABLED ? 'btn-ghost' : 'btn-primary'} w-full py-3`}
                >
                  {sending ? 'Sending link…' : 'Email me a sign-in link'}
                  {!sending && <ArrowRight />}
                </button>
              </form>
            </>
          )}

          {error && (
            <p role="alert" className="mt-4 text-center text-sm text-rose-300">
              {error}
            </p>
          )}
        </div>

        <div className="mt-8 flex justify-center gap-6 text-xs text-neutral-500">
          <span className="flex items-center gap-1.5">
            <Chapters className="h-3.5 w-3.5 text-accent" /> Summaries & chapters
          </span>
          <span className="flex items-center gap-1.5">
            <Chat className="h-3.5 w-3.5 text-accent" /> Ask with sources
          </span>
        </div>
      </main>
    </div>
  )
}
