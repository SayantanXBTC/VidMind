// Timeline steps mapped from the backend's real progress numbers.
//   YouTube: 5 queued → 15 reading transcript → 30–95 writing → 100
//   Upload:  8 extracting audio → 12–60 transcribing → 60–95 writing → 100
const STEPS = {
  youtube: [
    { key: 'fetch', label: 'Fetch video', threshold: 15 },
    { key: 'transcript', label: 'Read captions', threshold: 30 },
    { key: 'write', label: 'Write notes', threshold: 100 },
    { key: 'ready', label: 'Ready', threshold: 100 },
  ],
  upload: [
    { key: 'audio', label: 'Extract audio', threshold: 12 },
    { key: 'transcribe', label: 'Transcribe', threshold: 60 },
    { key: 'write', label: 'Write notes', threshold: 100 },
    { key: 'ready', label: 'Ready', threshold: 100 },
  ],
}

// Each step tagged 'done' | 'active' | 'pending', purely from real progress.
export function getTimelineSteps(progress, source = 'youtube') {
  const steps = STEPS[source] || STEPS.youtube
  const firstPendingIndex = steps.findIndex((step) => progress < step.threshold)
  return steps.map((step, idx) => {
    let state = 'pending'
    if (progress >= step.threshold) state = 'done'
    else if (idx === firstPendingIndex) state = 'active'
    return { ...step, state }
  })
}
