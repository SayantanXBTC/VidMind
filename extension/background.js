// Minimal MV3 service worker. The extension is otherwise popup-only (see
// README — no content script, no YouTube page injection); this just seeds
// default settings once on install so the popup always has a backend/app
// URL to fall back to before the user opens settings.
const DEFAULT_BACKEND_URL = 'http://localhost:8000'
const DEFAULT_FRONTEND_URL = 'http://localhost:5173'

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.sync.get(['backendUrl', 'frontendUrl'], (result) => {
    const updates = {}
    if (!result.backendUrl) updates.backendUrl = DEFAULT_BACKEND_URL
    if (!result.frontendUrl) updates.frontendUrl = DEFAULT_FRONTEND_URL
    if (Object.keys(updates).length) chrome.storage.sync.set(updates)
  })
})
