export const MAX_PDF_BYTES = 10485760
export function validatePdf(file) {
  if (!/\.pdf$/i.test(file.name) || (file.type && file.type !== 'application/pdf')) return 'Choose a PDF file.'
  if (file.size > MAX_PDF_BYTES) return 'Choose a PDF no larger than 10 MiB (10485760 bytes).'
  return ''
}
export function uploadError(status, body, kind) {
  if (kind === 'timeout') return 'The request timed out. Check your connection and retry.'
  if (kind === 'network') return 'Connection lost. Check your internet connection and retry.'
  let detail = ''
  try {
    const data = typeof body === 'string' ? JSON.parse(body) : body
    detail = typeof data?.detail === 'string' ? data.detail : Array.isArray(data?.detail)
      ? data.detail.map(item => typeof item === 'string' ? item : typeof item?.msg === 'string' ? item.msg : '').filter(Boolean).join('; ') : ''
  } catch { /* Never display upstream HTML. */ }
  if (status === 409) return 'You already uploaded a file with this name.'
  if (status === 413) return 'This file exceeds the 10 MiB (10485760 bytes) limit.'
  if (status === 503) return 'PDF storage is temporarily unavailable. Please retry shortly.'
  if (status === 422) return detail || 'This PDF could not be read. Try an unencrypted PDF with selectable text.'
  return detail || `Upload failed (${status || 'unknown error'}). Please retry.`
}
export function queueReducer(state, action) {
  if (action.type === 'start' && state.some(item => ['uploading', 'processing'].includes(item.status))) return state
  if (action.type === 'reset') return []
  if (action.type === 'add') return [...state, ...action.items]
  if (action.type === 'dismiss') return state.filter(item => item.id !== action.id || ['uploading', 'processing'].includes(item.status))
  return state.map(item => {
    if (item.id !== action.id) return item
    if (action.type === 'retry') return ['failed', 'cancelled'].includes(item.status) ? { ...item, status: 'queued', progress: 0, error: '' } : item
    if (action.type === 'start') return item.status === 'queued' ? { ...item, status: 'uploading', progress: 0 } : item
    if (action.type === 'progress') return item.status === 'uploading' ? { ...item, progress: Math.min(100, Math.max(item.progress, action.progress)) } : item
    if (action.type === 'processing') return item.status === 'uploading' ? { ...item, status: 'processing', progress: 100 } : item
    if (action.type === 'cancel') return item.status === 'uploading' ? { ...item, status: 'cancelled', error: 'Upload cancelled.' } : item
    if (action.type === 'ready' && ['processing', 'uploading'].includes(item.status)) return { ...item, status: 'ready', progress: 100, documentId: action.documentId }
    if (action.type === 'fail') return { ...item, status: 'failed', error: action.error }
    return item
  })
}
export function reconcileUpload(before, after, file) {
  const known = new Set(before.map(item => item.id))
  return after.find(item => !known.has(item.id) && item.filename === file.name && item.size_bytes === file.size)
}

export function shouldReconcileUpload(error) {
  // Browsers may retry a lost POST themselves, producing 409 after it committed.
  return Boolean(error.sent && (['network', 'timeout'].includes(error.kind) || error.status === 409))
}
