// Timeline steps mapped from the backend's real progress number
// (5 queued → 15 reading transcript → 30–95 writing notes → 100 ready).
const TIMELINE_STEPS = [
  { key: 'fetch', label: 'Fetch video', threshold: 15 },
  { key: 'transcript', label: 'Read transcript', threshold: 30 },
  { key: 'write', label: 'Write notes', threshold: 100 },
  { key: 'ready', label: 'Ready', threshold: 100 },
]

// Each step tagged 'done' | 'active' | 'pending', purely from real progress.
export function getTimelineSteps(progress) {
  const firstPendingIndex = TIMELINE_STEPS.findIndex((step) => progress < step.threshold)
  return TIMELINE_STEPS.map((step, idx) => {
    let state = 'pending'
    if (progress >= step.threshold) state = 'done'
    else if (idx === firstPendingIndex) state = 'active'
    return { ...step, state }
  })
}
