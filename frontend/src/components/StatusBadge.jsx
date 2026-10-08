const STYLES = {
  uploaded: { label: 'Queued', dot: 'bg-neutral-400', text: 'text-neutral-300', ring: 'ring-white/10' },
  processing: { label: 'Analyzing', dot: 'bg-accent animate-pulse', text: 'text-accent', ring: 'ring-accent/25' },
  completed: { label: 'Ready', dot: 'bg-emerald-400', text: 'text-emerald-300', ring: 'ring-emerald-400/20' },
  failed: { label: 'Failed', dot: 'bg-rose-400', text: 'text-rose-300', ring: 'ring-rose-400/25' },
}

export default function StatusBadge({ status, className = '' }) {
  const style = STYLES[status] || STYLES.uploaded
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full bg-ink-950/70 px-2.5 py-1 text-[11px] font-medium ring-1 ring-inset backdrop-blur-md ${style.ring} ${style.text} ${className}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} aria-hidden="true" />
      {style.label}
    </span>
  )
}
