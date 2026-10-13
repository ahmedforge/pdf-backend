import { normalizeSources } from './citations.js'

// Decode line-by-line so CRLF, JSON, events and UTF-8 can split across any read.
export async function readCitationStream(body, onUpdate, signal) {
  if (!body) throw new Error('No answer stream was received')
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = '', event = '', data = [], answer = '', sources = []
  let done = false, failure = '', gotSources = false
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
    if (type === 'sources') {
      if (!Array.isArray(value.sources)) throw new Error('The server returned invalid citation sources.')
      sources = normalizeSources(value.sources); gotSources = true
      onUpdate({ sources })
    } else if (type === 'token') {
      if (!gotSources || typeof value.text !== 'string') throw new Error('The server returned an invalid answer stream.')
      answer += value.text
      onUpdate({ answer })
    } else if (type === 'error') {
      failure = typeof value.message === 'string' && value.message ? value.message : 'Answer generation failed. Please retry.'
      onUpdate({ status: 'error', error: failure })
    } else if (type === 'done') {
      done = true
      if (!gotSources || value.complete !== true) failure ||= 'Answer generation was interrupted. Please retry.'
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
      const chunk = await reader.read()
      checkAbort()
      if (chunk.done) { buffer += decoder.decode(); consume(true); dispatch(); break }
      buffer += decoder.decode(chunk.value, { stream: true }); consume()
    }
    if (failure) throw new Error(failure)
    if (!done) throw new Error('The answer stream ended before completion. Please retry.')
    if (!answer.trim()) throw new Error('No answer was received. Please retry.')
    return { answer, sources }
  } finally {
    signal.removeEventListener('abort', cancel)
    try { await reader.cancel() } catch { /* Connection already closed. */ }
    reader.releaseLock()
  }
}
