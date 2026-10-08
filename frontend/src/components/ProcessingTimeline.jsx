import ProgressBar from './ProgressBar.jsx'
import { Check } from './Icons.jsx'
import { getTimelineSteps } from '../utils/stage.js'

export default function ProcessingTimeline({ progress, stage }) {
  const steps = getTimelineSteps(progress)

  return (
    <div className="card relative overflow-hidden p-6 sm:p-8">
      <div className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full bg-accent-strong/20 blur-3xl" />
      <div className="relative">
        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="eyebrow">Analyzing</p>
            <p className="mt-2 font-display text-3xl text-neutral-50 sm:text-4xl">
              {stage || 'Analyzing'}
              <span className="animate-pulse text-accent">…</span>
            </p>
          </div>
          <p className="font-mono text-2xl tabular-nums text-neutral-500">{progress}%</p>
        </div>

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
                aria-hidden="true"
              >
                {step.state === 'done' ? (
                  <Check className="h-3 w-3" strokeWidth={2.4} />
                ) : (
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${step.state === 'active' ? 'animate-pulse bg-accent' : 'bg-neutral-700'}`}
                  />
                )}
              </span>
              <span
                className={`text-[11px] font-medium leading-tight sm:text-xs ${
                  step.state === 'pending' ? 'text-neutral-600' : 'text-neutral-300'
                }`}
              >
                {step.label}
              </span>
            </li>
          ))}
        </ol>
      </div>
    </div>
  )
}
