import { getAccessToken, supabase } from './supabase.js'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

if (window.location.protocol === 'https:' && API_URL.startsWith('http://')) {
  // Browsers block these requests as mixed content; make the cause obvious.
  console.error(`VITE_API_URL must use https:// on an https site (got ${API_URL}).`)
}

const NETWORK_ERROR = "Can't reach VidMind right now. Check your connection and try again."

async function authHeaders() {
  const token = await getAccessToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function handleResponse(response) {
  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`
    try {
      const body = await response.json()
      detail = body.detail || detail
    } catch {
      // response had no JSON body
    }
    if (response.status === 401 && supabase) {
      // Session is gone or invalid server-side; return to the sign-in screen.
      await supabase.auth.signOut()
    }
    throw new Error(detail)
  }
  if (response.status === 204) return null
  return response.json()
}

async function request(path, { method = 'GET', body } = {}) {
  const headers = await authHeaders()
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  let response
  try {
    response = await fetch(`${API_URL}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new Error(NETWORK_ERROR)
  }
  return handleResponse(response)
}

export const healthCheck = () => request('/api/health')
export const getAccount = () => request('/api/me')
export const getVideos = () => request('/api/videos')
export const getVideo = (videoId) => request(`/api/videos/${videoId}`)
export const deleteVideo = (videoId) => request(`/api/videos/${videoId}`, { method: 'DELETE' })
export const retryVideo = (videoId) => request(`/api/videos/${videoId}/retry`, { method: 'POST' })
export const getVideoStatus = (videoId) => request(`/api/videos/${videoId}/status`)
export const getTranscript = (videoId) => request(`/api/videos/${videoId}/transcript`)
export const getSummary = (videoId) => request(`/api/videos/${videoId}/summary`)

export const searchVideo = (videoId, query, topK = 5) =>
  request(`/api/videos/${videoId}/search`, { method: 'POST', body: { query, top_k: topK } })

export const askVideo = (videoId, question) =>
  request(`/api/videos/${videoId}/ask`, { method: 'POST', body: { question } })

export const analyzeYoutubeUrl = (url) =>
  request('/api/videos/youtube', { method: 'POST', body: { url } })

/** <video src> can't send headers, so the token rides along as a query parameter. */
export function getVideoFileUrl(videoId, accessToken) {
  const base = `${API_URL}/api/videos/${videoId}/file`
  return accessToken ? `${base}?access_token=${encodeURIComponent(accessToken)}` : base
}

export async function uploadVideo(file, onProgress) {
  const headers = await authHeaders()
  return new Promise((resolve, reject) => {
    const formData = new FormData()
    formData.append('file', file)

    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_URL}/api/videos/upload`)
    Object.entries(headers).forEach(([name, value]) => xhr.setRequestHeader(name, value))

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.round((event.loaded / event.total) * 100))
      }
    }

    xhr.onload = () => {
      let body = null
      try {
        body = JSON.parse(xhr.responseText)
      } catch {
        // ignore parse failure, handled below
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body)
      } else {
        reject(new Error(body?.detail || `Upload failed with status ${xhr.status}`))
      }
    }

    xhr.onerror = () => reject(new Error(NETWORK_ERROR))

    xhr.send(formData)
  })
}
