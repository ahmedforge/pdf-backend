import { normalizeSources } from './citations.js'

export const INCOMPATIBLE_STREAM = 'The backend does not support structured citation streaming (sources and done events are required). Please retry after updating the backend.'

export async function requestCitationStream(request, documentId, token, question, onUpdate, signal) {
  let response
  try {
    response = await request(`/files/${documentId}/ask/stream?format=sse`, {
      method: 'POST', signal,
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify({ question, top_k: 3 }),
    })
  } catch (error) {
    if ([404, 422].includes(error.status)) throw new Error(`${INCOMPATIBLE_STREAM} (HTTP ${error.status})`, { cause: error })
    throw error
  }
  if (!response.ok || response.headers.get('content-type')?.split(';')[0].trim().toLowerCase() !== 'text/event-stream') {
    try { await response.body?.cancel() } catch { /* Already closed. */ }
    throw new Error([404, 422].includes(response.status) ? `${INCOMPATIBLE_STREAM} (HTTP ${response.status})` : INCOMPATIBLE_STREAM)
  }
  return readCitationStream(response.body, onUpdate, signal)
}

// Decode line-by-line so CRLF, JSON, events and UTF-8 can split across any read.
export async function readCitationStream(body, onUpdate, signal, { sourcesTimeoutMs = 30000, idleTimeoutMs = 30000, totalTimeoutMs = 180000 } = {}) {
  if (!body) throw new Error(INCOMPATIBLE_STREAM)
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = '', event = '', data = [], answer = '', sources = []
  let done = false, failure = '', gotSources = false
  const started = Date.now()
  let lastEvent = started
  const checkAbort = () => { if (signal.aborted) throw new DOMException('Stopped', 'AbortError') }
  const cancel = () => { reader.cancel().catch(() => {}) }
  signal.addEventListener('abort', cancel, { once: true })
  function dispatch() {
    if (!data.length) { event = ''; return }
    let value
    try { value = JSON.parse(data.join('\n')) } catch { throw new Error('The server returned an invalid answer event. Please retry.') }
    const type = event
    event = ''; data = []
    if (done) return
    if (!value || typeof value !== 'object') throw new Error('The server returned an invalid answer event. Please retry.')
    if (['sources', 'token', 'error', 'done'].includes(type)) lastEvent = Date.now()
    if (type === 'sources') {
      if (!Array.isArray(value.sources)) throw new Error('The server returned invalid citation sources.')
      sources = normalizeSources(value.sources); gotSources = true
      onUpdate({ sources })
    } else if (type === 'token') {
      if (!gotSources) throw new Error(INCOMPATIBLE_STREAM)
      if (typeof value.text !== 'string') throw new Error('The server returned an invalid answer stream.')
      answer += value.text
      onUpdate({ answer })
    } else if (type === 'error') {
      failure = typeof value.message === 'string' && value.message ? value.message : 'Answer generation failed. Please retry.'
      onUpdate({ status: 'error', error: failure })
      throw new Error(failure)
    } else if (type === 'done') {
      done = true
      if (!gotSources) throw new Error(INCOMPATIBLE_STREAM)
      if (value.complete !== true) failure ||= 'Answer generation was interrupted. Please retry.'
    }
  }
  function line(value) {
    if (value === '') dispatch()
    else if (value.startsWith('event:')) event = value.slice(6).trim()
    else if (value.startsWith('data:')) data.push(value.slice(5).replace(/^ /, ''))
  }
  function consume(final = false) {
    let index
    while ((index = buffer.search(/[\r\n]/)) >= 0) {
      if (!final && buffer[index] === '\r' && index === buffer.length - 1) break
      const length = buffer[index] === '\r' && buffer[index+1] === '\n' ? 2 : 1
      line(buffer.slice(0, index)); buffer = buffer.slice(index + length)
    }
    if (final && buffer) { line(buffer); buffer = '' }
  }
  try {
    while (!done) {
      checkAbort()
      const deadline = Math.min(started + totalTimeoutMs, gotSources ? lastEvent + idleTimeoutMs : started + sourcesTimeoutMs)
      if (Date.now() >= deadline) throw new Error(gotSources
        ? 'The answer stream timed out before completion (missing token or done event). Please retry.'
        : INCOMPATIBLE_STREAM)
      let timer
      let chunk
      try {
        chunk = await Promise.race([
          reader.read(),
          new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(gotSources
            ? 'The answer stream timed out before completion (missing token or done event). Please retry.'
            : INCOMPATIBLE_STREAM)), Math.max(0, deadline - Date.now())) }),
        ])
      } finally { clearTimeout(timer) }
      checkAbort()
      if (chunk.done) { buffer += decoder.decode(); consume(true); dispatch(); break }
      buffer += decoder.decode(chunk.value, { stream: true }); consume()
    }
    if (failure) throw new Error(failure)
    if (!gotSources) throw new Error(INCOMPATIBLE_STREAM)
    if (!done) throw new Error('The answer stream ended before completion. Please retry.')
    if (!answer.trim()) throw new Error('No answer was received. Please retry.')
    return { answer, sources }
  } finally {
    signal.removeEventListener('abort', cancel)
    try { await reader.cancel() } catch { /* Connection already closed. */ }
    reader.releaseLock()
  }
}
