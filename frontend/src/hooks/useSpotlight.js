import { useCallback } from 'react'

/** Feeds the cursor position to a `.spotlight` element as --x / --y. */
export default function useSpotlight() {
  return useCallback((event) => {
    const el = event.currentTarget
    const rect = el.getBoundingClientRect()
    el.style.setProperty('--x', `${event.clientX - rect.left}px`)
    el.style.setProperty('--y', `${event.clientY - rect.top}px`)
  }, [])
}
