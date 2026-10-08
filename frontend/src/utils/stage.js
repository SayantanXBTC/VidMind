// Maps the backend's real progress number to UI text. Thresholds match the
// checkpoints processing_service.py writes to the DB (5/20/45/60, then 60-85
// while the LLM streams the notes, 85/100) — the UI never shows a stage the
// backend hasn't reached.
export function stageLabel(progress, sourceType = 'upload') {
  const isYoutube = sourceType === 'youtube'
  if (progress < 20) return isYoutube ? 'Fetching captions' : 'Extracting audio'
  if (progress < 45) return isYoutube ? 'Reading transcript' : 'Transcribing speech'
  if (progress < 60) return 'Building search index'
  if (progress < 85) return 'Writing summary & chapters'
  if (progress < 100) return 'Finishing up'
  return 'Ready'
}

const TIMELINE_STEPS = [
  { key: 'ingest', label: 'Ingest', threshold: 20 },
  { key: 'transcribe', label: 'Transcribe', threshold: 45 },
  { key: 'index', label: 'Index', threshold: 60 },
  { key: 'write', label: 'Write notes', threshold: 85 },
  { key: 'ready', label: 'Ready', threshold: 100 },
]

// Returns each timeline step tagged 'done' | 'active' | 'pending', purely
// from the real progress number — no invented intermediate state.
export function getTimelineSteps(progress) {
  const firstPendingIndex = TIMELINE_STEPS.findIndex((step) => progress < step.threshold)
  return TIMELINE_STEPS.map((step, idx) => {
    let state = 'pending'
    if (progress >= step.threshold) state = 'done'
    else if (idx === firstPendingIndex) state = 'active'
    return { ...step, state }
  })
}
