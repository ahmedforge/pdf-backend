import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { apiRequest } from '@/api'
import { historyScope, loadHistories, saveHistories, STORAGE_WARNING } from '@/lib/chat-storage'
import { readCitationStream } from '@/lib/sse-stream'
import { chatReducer } from '@/lib/chat-state'

export function useDocumentChat(token) {
  const scope = historyScope(token)
  const read = () => {
    try { return loadHistories(localStorage, scope) }
    catch { return { history: {}, warning: STORAGE_WARNING } }
  }
  const [initial] = useState(read)
  const [conversations, dispatch] = useReducer(chatReducer, initial.history)
  const [readWarning, setReadWarning] = useState(initial.warning)
  const [storageWarning, setStorageWarning] = useState('')
  const currentScope = useRef(scope)
  const skipSave = useRef(false)

  useEffect(() => {
    if (currentScope.current === scope) return
    currentScope.current = scope
    skipSave.current = true
    let loaded
    try { loaded = loadHistories(localStorage, scope) }
    catch { loaded = { history: {}, warning: STORAGE_WARNING } }
    dispatch({ type: 'hydrate', history: loaded.history })
    const timer = setTimeout(() => setReadWarning(loaded.warning), 0)
    return () => clearTimeout(timer)
  }, [scope])

  useEffect(() => {
    if (currentScope.current !== scope) return
    if (skipSave.current) { skipSave.current = false; return }
    const timer = setTimeout(() => {
      try { setStorageWarning(saveHistories(localStorage, scope, conversations)) }
      catch { setStorageWarning(STORAGE_WARNING) }
    }, 100)
    return () => clearTimeout(timer)
  }, [conversations, scope])
  const [drafts, setDrafts] = useState({})
  const [activeDocument, setActiveDocument] = useState(null)
  const request = useRef(null)

  useEffect(() => () => { request.current?.controller.abort(); request.current = null }, [])

  const stop = useCallback(() => {
    const current = request.current
    if (!current) return
    request.current = null
    current.controller.abort()
    dispatch({ type: 'update', documentId: current.documentId, id: current.id, update: { status: 'stopped' } })
    setActiveDocument(null)
  }, [])

  const reset = useCallback(() => {
    stop()
    dispatch({ type: 'reset' })
    setDrafts({})
    setReadWarning('')
  }, [stop])

  async function send(documentId, question, retryId) {
    if (!documentId || !question.trim() || request.current) return
    const current = { documentId, id: crypto.randomUUID(), controller: new AbortController() }
    request.current = current
    setActiveDocument(documentId)
    const start = { type: 'start', documentId, id: current.id, question: question.trim(), retryId }
    dispatch(start)
    try { setStorageWarning(saveHistories(localStorage, scope, chatReducer(conversations, start))) }
    catch { setStorageWarning(STORAGE_WARNING) }
    if (!retryId) setDrafts(old => ({ ...old, [documentId]: '' }))
    const update = value => {
      if (request.current === current) dispatch({ type: 'update', documentId, id: current.id, update: value })
    }
    try {
      const response = await apiRequest(`/files/${documentId}/ask/stream?format=sse`, {
        method: 'POST', signal: current.controller.signal,
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify({ question: question.trim(), top_k: 3 }),
      })
      if (!response.headers.get('content-type')?.includes('text/event-stream')) throw new Error('The server does not support citation streaming yet. Please retry after deployment.')
      await readCitationStream(response.body, update, current.controller.signal)
      update({ status: 'complete' })
    } catch (error) {
      update({ status: error.name === 'AbortError' ? 'stopped' : 'error', error: error.name === 'AbortError' ? '' : error.message })
    } finally {
      if (request.current === current) {
        request.current = null
        setActiveDocument(null)
      }
    }
  }

  return { conversations, drafts, activeDocument, storageWarning: readWarning || storageWarning, send, stop, reset,
    clear: id => {
      stop()
      dispatch({ type: 'clear', documentId: id })
      try { setStorageWarning(saveHistories(localStorage, scope, { [id]: [] })) }
      catch { setStorageWarning(STORAGE_WARNING) }
    },
    setDraft: (id, text) => setDrafts(old => ({ ...old, [id]: text })) }
}
