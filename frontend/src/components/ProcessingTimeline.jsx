import ProgressBar from './ProgressBar.jsx'
import { Check } from './Icons.jsx'
import { getTimelineSteps } from '../utils/stage.js'

/** Orbiting rings around a glowing core: the "thinking" visual. */
function Orb({ progress }) {
  return (
    <div className="relative mx-auto h-40 w-40 shrink-0 sm:mx-0" aria-hidden="true">
      <div className="absolute inset-6 animate-pulse-ring rounded-full border border-accent/40" />
      <div className="absolute inset-6 animate-pulse-ring rounded-full border border-aqua/30 [animation-delay:1.2s]" />
      <div className="absolute inset-0 animate-orbit rounded-full border border-dashed border-white/10">
        <span className="absolute -top-1 left-1/2 h-2 w-2 -translate-x-1/2 rounded-full bg-accent shadow-[0_0_12px_2px_rgba(185,166,255,0.8)]" />
      </div>
      <div className="absolute inset-5 animate-orbit-fast rounded-full border border-white/[0.06] [animation-direction:reverse]">
        <span className="absolute -bottom-1 left-1/2 h-1.5 w-1.5 -translate-x-1/2 rounded-full bg-aqua shadow-[0_0_10px_2px_rgba(127,231,255,0.7)]" />
      </div>
      <div className="absolute inset-12 rounded-full bg-[radial-gradient(circle_at_35%_30%,#ffffff_0%,#c9bbff_22%,#8b6cff_55%,#2a1e66_100%)] shadow-glow-lg" />
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="font-mono text-sm font-medium tabular-nums text-white drop-shadow">{progress}%</span>
      </div>
    </div>
  )
}

export default function ProcessingTimeline({ progress, stage, source }) {
  const steps = getTimelineSteps(progress, source)
  const hint =
    source === 'upload'
      ? 'Transcribing takes roughly a quarter of the video’s length. You can leave this page — it will be waiting in your library.'
      : 'Usually about 30 seconds. You can leave this page — it will be waiting in your library.'

  return (
    <div className="glow-border rounded-[2rem]">
      <div className="relative overflow-hidden rounded-[2rem] bg-ink-900/90 p-6 backdrop-blur-xl sm:p-10">
        <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-accent-strong/20 blur-3xl" />
        <div className="relative flex flex-col items-center gap-8 sm:flex-row sm:items-center">
          <Orb progress={progress} />
          <div className="w-full min-w-0 flex-1">
            <p className="eyebrow">Analyzing</p>
            <p className="mt-2 font-display text-3xl text-neutral-50 sm:text-4xl">
              {stage || 'Analyzing'}
              <span className="animate-pulse text-accent">…</span>
            </p>
            <ProgressBar progress={progress} className="mt-6" />
            <ol className="mt-6 grid grid-cols-4 gap-2">
              {steps.map((step) => (
                <li key={step.key} className="flex flex-col items-start gap-2">
                  <span
                    className={`flex h-6 w-6 items-center justify-center rounded-full border text-[10px] transition-colors ${
                      step.state === 'done'
                        ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300'
                        : step.state === 'active'
                          ? 'border-accent/50 bg-accent/10 text-accent shadow-glow'
                          : 'border-white/10 text-neutral-600'
                    }`}
                  >
                    {step.state === 'done' ? (
                      <Check className="h-3 w-3" strokeWidth={2.4} />
                    ) : (
                      <span className={`h-1.5 w-1.5 rounded-full ${step.state === 'active' ? 'animate-pulse bg-accent' : 'bg-neutral-700'}`} />
                    )}
                  </span>
                  <span className={`text-[11px] font-medium leading-tight sm:text-xs ${step.state === 'pending' ? 'text-neutral-600' : 'text-neutral-300'}`}>
                    {step.label}
                  </span>
                </li>
              ))}
            </ol>
            <p className="mt-6 text-[13px] leading-relaxed text-neutral-500">{hint}</p>
          </div>
        </div>
      </div>
    </div>
  )
}
