import { useEffect, useReducer, useRef } from 'react'
import { API_BASE_URL, apiRequest } from '@/api'
import { queueReducer, reconcileUpload, validatePdf, uploadError, shouldReconcileUpload } from '@/lib/upload-state'
import { uploadPdf } from '@/lib/upload-request'

export function useUploadQueue(token, onReady) {
  const [items, dispatch] = useReducer(queueReducer, [])
  const current = useRef(null)
  const previousToken = useRef(token)
  const ready = useRef(onReady)
  useEffect(() => { ready.current = onReady }, [onReady])
  useEffect(() => {
    if (previousToken.current !== token) { previousToken.current = token; dispatch({ type: 'reset' }) }
    return () => { current.current?.request?.dispose(); current.current = null }
  }, [token])
  useEffect(() => {
    if (!token || current.current) return
    // A queue belongs to the account that selected its files.
    if (items.some(item => item.token !== token)) return
    const item = items.find(item => item.status === 'queued')
    if (!item) return
    const running = { id: item.id }; current.current = running
    const active = () => current.current === running
    const list = async () => (await (await apiRequest('/files', { headers: { Authorization: `Bearer ${token}` } })).json()).files || []
    async function run() {
      dispatch({ type: 'start', id: item.id })
      let before
      try {
        before = await list()
        if (!active()) return
        running.request = uploadPdf(API_BASE_URL, token, item.file, {
          onProgress: progress => { if (active()) dispatch({ type: 'progress', id: item.id, progress }) },
          onProcessing: () => { if (active()) dispatch({ type: 'processing', id: item.id }) },
        })
        const result = await running.request.promise
        if (active()) { dispatch({ type: 'ready', id: item.id, documentId: result.document_id }); ready.current(result) }
      } catch (error) {
        if (!active()) return
        if (error.kind === 'abort') return
        if (shouldReconcileUpload(error)) {
          try {
            const recovered = reconcileUpload(before, await list(), item.file)
            if (recovered && active()) {
              dispatch({ type: 'ready', id: item.id, documentId: recovered.id })
              ready.current({ ...recovered, document_id: recovered.id }); return
            }
          } catch { /* Preserve the original error, with explicit uncertainty. */ }
          if (['network', 'timeout'].includes(error.kind)) error.message += ' The server may still be processing it. Refresh your library before retrying.'
        }
        if (active()) dispatch({ type: 'fail', id: item.id, error: error.status || error.kind ? error.message : uploadError(0, '', 'network') })
      } finally { if (active()) current.current = null }
    }
    run()
  }, [items, token])
  return { items,
    add: files => dispatch({ type: 'add', items: Array.from(files).map(file => {
      const error = validatePdf(file)
      return { id: crypto.randomUUID(), token, file, status: error ? 'failed' : 'queued', progress: 0, error }
    }) }),
    retry: item => { const error = validatePdf(item.file); if (error) dispatch({ type: 'fail', id: item.id, error }); else dispatch({ type: 'retry', id: item.id }) },
    dismiss: id => dispatch({ type: 'dismiss', id }),
    cancel: id => {
      const running = current.current
      if (running?.id === id && (!running.request || running.request.cancel())) {
        current.current = null; dispatch({ type: 'cancel', id })
      }
    },
    reset: () => { current.current?.request?.dispose(); current.current = null; dispatch({ type: 'reset' }) },
  }
}
