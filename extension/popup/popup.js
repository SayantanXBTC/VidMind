const DEFAULT_BACKEND_URL = 'http://localhost:8000'
const DEFAULT_FRONTEND_URL = 'http://localhost:5173'
const POLL_INTERVAL_MS = 2000

const YOUTUBE_URL_RE =
  /^https?:\/\/(www\.|m\.)?(youtube\.com\/(watch\?v=|shorts\/)|youtu\.be\/)([A-Za-z0-9_-]{11})/

const contentEl = document.getElementById('content')
const statusTextEl = document.getElementById('status-text')
const settingsToggle = document.getElementById('settings-toggle')
const settingsPanel = document.getElementById('settings')
const backendUrlInput = document.getElementById('backend-url')
const frontendUrlInput = document.getElementById('frontend-url')
const settingsSave = document.getElementById('settings-save')

let backendUrl = DEFAULT_BACKEND_URL
let frontendUrl = DEFAULT_FRONTEND_URL
let pollTimer = null

function stageLabel(progress) {
  if (progress < 20) return 'Fetching transcript…'
  if (progress < 45) return 'Fetching transcript…'
  if (progress < 60) return 'Building semantic index…'
  if (progress < 85) return 'Generating summary…'
  if (progress < 100) return 'Finalizing…'
  return 'Ready'
}

function extractVideoId(url) {
  const match = YOUTUBE_URL_RE.exec(url || '')
  return match ? match[4] : null
}

async function loadSettings() {
  return new Promise((resolve) => {
    chrome.storage.sync.get(['backendUrl', 'frontendUrl'], (result) => {
      backendUrl = result.backendUrl || DEFAULT_BACKEND_URL
      frontendUrl = result.frontendUrl || DEFAULT_FRONTEND_URL
      backendUrlInput.value = backendUrl
      frontendUrlInput.value = frontendUrl
      resolve()
    })
  })
}

settingsToggle.addEventListener('click', () => {
  settingsPanel.classList.toggle('hidden')
})

settingsSave.addEventListener('click', () => {
  const newBackend = backendUrlInput.value.trim() || DEFAULT_BACKEND_URL
  const newFrontend = frontendUrlInput.value.trim() || DEFAULT_FRONTEND_URL
  chrome.storage.sync.set({ backendUrl: newBackend, frontendUrl: newFrontend }, () => {
    backendUrl = newBackend
    frontendUrl = newFrontend
    settingsPanel.classList.add('hidden')
  })
})

function renderNotYoutube() {
  statusTextEl.textContent = 'Open a YouTube video to analyze it with VidMind.'
}

function renderReady(tabUrl, title) {
  contentEl.innerHTML = `
    <div class="card">
      <p class="video-title">${escapeHtml(title || tabUrl)}</p>
      <button id="analyze-btn" class="btn btn-primary">Analyze with VidMind</button>
    </div>
  `
  document.getElementById('analyze-btn').addEventListener('click', () => startAnalysis(tabUrl))
}

function renderProcessing(progress) {
  contentEl.innerHTML = `
    <div class="card">
      <div class="stage-line"><span class="spinner"></span><span id="stage-text">${stageLabel(progress)}</span></div>
      <div class="progress-track"><div class="progress-fill" style="width:${progress}%"></div></div>
      <p class="muted">Analyzing video</p>
    </div>
  `
}

function renderCompleted(id, summaryText) {
  contentEl.innerHTML = `
    <div class="card">
      <p class="ready-line">✓ Analysis ready</p>
      ${summaryText ? `<p class="summary-text">${escapeHtml(summaryText)}</p>` : ''}
      <button id="open-full-btn" class="btn btn-primary">Open Full Analysis</button>
    </div>
  `
  document.getElementById('open-full-btn').addEventListener('click', () => {
    chrome.tabs.create({ url: `${frontendUrl}/videos/${id}` })
  })
}

function renderFailed(message) {
  contentEl.innerHTML = `
    <div class="card">
      <p class="error-text">${escapeHtml(message || 'Something went wrong while processing this video.')}</p>
      <button id="open-full-btn" class="btn btn-secondary">Open VidMind</button>
    </div>
  `
  document.getElementById('open-full-btn').addEventListener('click', () => {
    chrome.tabs.create({ url: frontendUrl })
  })
}

function escapeHtml(str) {
  const div = document.createElement('div')
  div.textContent = str
  return div.innerHTML
}

async function startAnalysis(url) {
  renderProcessing(5)
  try {
    const response = await fetch(`${backendUrl}/api/videos/youtube`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    })
    const body = await response.json().catch(() => null)
    if (!response.ok) {
      throw new Error(body?.detail || `Request failed with status ${response.status}`)
    }
    pollStatus(body.id)
  } catch (err) {
    renderFailed(err.message)
  }
}

function pollStatus(id) {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = setInterval(async () => {
    try {
      const response = await fetch(`${backendUrl}/api/videos/${id}/status`)
      const status = await response.json()
      if (status.status === 'completed') {
        clearInterval(pollTimer)
        let summaryText = ''
        try {
          const summaryRes = await fetch(`${backendUrl}/api/videos/${id}/summary`)
          if (summaryRes.ok) {
            const summary = await summaryRes.json()
            summaryText = summary.summary
          }
        } catch {
          // summary fetch failing shouldn't block "ready" state
        }
        renderCompleted(id, summaryText)
      } else if (status.status === 'failed') {
        clearInterval(pollTimer)
        renderFailed(status.error)
      } else {
        renderProcessing(status.progress)
      }
    } catch {
      // transient network hiccup — keep polling, don't flash an error
    }
  }, POLL_INTERVAL_MS)
}

async function init() {
  await loadSettings()

  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tab = tabs[0]
    const videoId = tab ? extractVideoId(tab.url) : null

    if (!videoId) {
      renderNotYoutube()
      return
    }

    statusTextEl.textContent = ''
    renderReady(tab.url, tab.title)
  })
}

init()
