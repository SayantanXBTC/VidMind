/**
 * The visitor's library, stored in this browser (IndexedDB) — there are no
 * accounts. Each entry is one YouTube video:
 *   { id, video, status, result?, error?, savedAt }
 * Clearing site data clears the library; the briefs themselves can always be
 * reopened from their link, since the server caches them by video.
 */
const DB_NAME = 'vidmind'
const STORE = 'library'
const CHANGE_EVENT = 'vidmind:library-changed'

let dbPromise = null

function openDb() {
  if (!dbPromise) {
    dbPromise = new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, 1)
      req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: 'id' })
      req.onsuccess = () => resolve(req.result)
      req.onerror = () => reject(req.error)
    }).catch((err) => {
      dbPromise = null
      throw err
    })
  }
  return dbPromise
}

// Some browsers (private modes, embedded or headless browsers) leave
// IndexedDB requests pending forever. Never let storage block the page.
const STORAGE_TIMEOUT_MS = 3000

function withTimeout(promise) {
  return Promise.race([
    promise,
    new Promise((_, reject) => setTimeout(() => reject(new Error('storage timeout')), STORAGE_TIMEOUT_MS)),
  ])
}

async function run(mode, fn) {
  const db = await withTimeout(openDb())
  return withTimeout(
    new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, mode)
      const request = fn(tx.objectStore(STORE))
      tx.oncomplete = () => resolve(request ? request.result : undefined)
      tx.onerror = () => reject(tx.error)
      tx.onabort = () => reject(tx.error)
    })
  )
}

function notify() {
  window.dispatchEvent(new Event(CHANGE_EVENT))
}

export async function listEntries() {
  try {
    const all = await run('readonly', (store) => store.getAll())
    return (all || []).sort((a, b) => b.savedAt - a.savedAt)
  } catch {
    return [] // private mode or storage blocked: the app still works, just without a library
  }
}

export async function getEntry(id) {
  try {
    return (await run('readonly', (store) => store.get(id))) || null
  } catch {
    return null
  }
}

/** Insert or update an entry, keeping its original savedAt. */
export async function saveEntry(entry) {
  try {
    const existing = await getEntry(entry.id)
    await run('readwrite', (store) =>
      store.put({ ...existing, ...entry, savedAt: existing?.savedAt ?? Date.now() })
    )
    notify()
  } catch {
    // storage unavailable or full; the current page keeps working
  }
}

export async function deleteEntries(ids) {
  try {
    await run('readwrite', (store) => {
      ids.forEach((id) => store.delete(id))
    })
    notify()
  } catch {
    // ignore
  }
}

export function onLibraryChange(callback) {
  window.addEventListener(CHANGE_EVENT, callback)
  return () => window.removeEventListener(CHANGE_EVENT, callback)
}
