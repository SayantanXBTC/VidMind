export default function ProgressBar({ progress, label, className = '' }) {
  return (
    <div className={className}>
      {label && (
        <div className="mb-2 flex items-baseline justify-between gap-3">
          <p className="truncate text-xs text-neutral-400">{label}</p>
          <p className="font-mono text-[11px] tabular-nums text-neutral-500">{progress}%</p>
        </div>
      )}
      <div
        className="relative h-1 w-full overflow-hidden rounded-full bg-white/[0.07]"
        role="progressbar"
        aria-valuenow={progress}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label || 'Progress'}
      >
        <div
          className="relative h-full overflow-hidden rounded-full bg-gradient-to-r from-accent-strong to-accent transition-[width] duration-700 ease-out"
          style={{ width: `${Math.max(progress, 3)}%` }}
        >
          <span className="absolute inset-y-0 left-0 w-1/2 animate-progress-sheen bg-gradient-to-r from-transparent via-white/40 to-transparent" />
        </div>
      </div>
    </div>
  )
}
