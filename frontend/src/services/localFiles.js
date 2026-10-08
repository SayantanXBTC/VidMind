/**
 * Uploaded files are never stored on the server, so an upload's video can
 * only play from the visitor's own computer. This keeps the picked file for
 * the current tab session, keyed by the upload's ID.
 */
const files = new Map()

export function rememberFile(id, file) {
  const previous = files.get(id)
  if (previous) URL.revokeObjectURL(previous.url)
  const entry = { file, url: URL.createObjectURL(file) }
  files.set(id, entry)
  return entry.url
}

export function fileUrl(id) {
  return files.get(id)?.url ?? null
}
