const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

if (window.location.protocol === 'https:' && API_URL.startsWith('http://')) {
  // Browsers block these requests as mixed content; make the cause obvious.
  console.error(`VITE_API_URL must use https:// on an https site (got ${API_URL}).`)
}

const NETWORK_ERROR = "Can't reach VidMind right now. Check your connection and try again."

/** Error carrying the HTTP status, so callers can react to e.g. 404 or 429. */
export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

async function request(path, { method = 'GET', body } = {}) {
  let response
  try {
    response = await fetch(`${API_URL}${path}`, {
      method,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError(NETWORK_ERROR, 0)
  }
  if (!response.ok) {
    let detail = `Request failed (${response.status})`
    try {
      const data = await response.json()
      if (typeof data.detail === 'string') detail = data.detail
    } catch {
      // no JSON body
    }
    throw new ApiError(detail, response.status)
  }
  return response.json()
}

/** Start (or reuse) the analysis of a YouTube video. Returns the job. */
export const analyzeVideo = (url) => request('/api/analyze', { method: 'POST', body: { url } })

/** Job status; includes the full result once completed (unless includeResult is false). */
export const getVideo = (videoId, { includeResult = true } = {}) =>
  request(`/api/videos/${encodeURIComponent(videoId)}${includeResult ? '' : '?include_result=false'}`)

export const askVideo = (videoId, question) =>
  request(`/api/videos/${encodeURIComponent(videoId)}/ask`, { method: 'POST', body: { question } })

export const getUsage = () => request('/api/usage')

/** Upload a video file from the visitor's computer. onProgress(0–100) while sending. */
export function uploadVideo(file, onProgress) {
  return new Promise((resolve, reject) => {
    const form = new FormData()
    form.append('file', file)
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_URL}/api/upload`)
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(Math.round((event.loaded / event.total) * 100))
    }
    xhr.onload = () => {
      let body = null
      try {
        body = JSON.parse(xhr.responseText)
      } catch {
        // no JSON body
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body)
      else reject(new ApiError(typeof body?.detail === 'string' ? body.detail : `Upload failed (${xhr.status})`, xhr.status))
    }
    xhr.onerror = () => reject(new ApiError(NETWORK_ERROR, 0))
    xhr.send(form)
  })
}

export const youtubeUrl = (videoId) => `https://www.youtube.com/watch?v=${videoId}`
