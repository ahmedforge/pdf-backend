import test from 'node:test'
import assert from 'node:assert/strict'
import { readCitationStream } from '../src/lib/sse-stream.js'
const event = (type, data) => `event: ${type}\r\ndata: ${JSON.stringify(data)}\r\n\r\n`
function body(text) {
  return new ReadableStream({ start(c) { for (const byte of new TextEncoder().encode(text)) c.enqueue(new Uint8Array([byte])); c.close() } })
}
test('SSE survives one-byte UTF-8, CRLF, JSON, and event boundary splits', async () => {
  const updates = []
  const text = event('sources', { sources: [{ chunk_index: 25, page: 7, text: 'Café' }] }) + event('token', { text: 'Café [Chu' }) + event('token', { text: 'nk 25]' }) + event('done', { complete: true })
  const result = await readCitationStream(body(text), update => updates.push(update), new AbortController().signal)
  assert.equal(result.answer, 'Café [Chunk 25]')
  assert.equal(result.sources[0].page, 7)
  assert.equal(updates[0].sources[0].chunk_index, 25)
})
test('error and unsuccessful/missing done events fail visibly while preserving partial content', async () => {
  const prefix = event('sources', { sources: [] }) + event('token', { text: 'Partial answer' })
  const updates = []
  await assert.rejects(readCitationStream(body(prefix + event('error', { message: 'Retry this answer' }) + event('done', { complete: false })), u => updates.push(u), new AbortController().signal), /Retry this answer/)
  assert.ok(updates.some(u => u.answer === 'Partial answer'))
  assert.ok(updates.some(u => u.status === 'error'))
  await assert.rejects(readCitationStream(body(prefix), () => {}, new AbortController().signal), /before completion/)
  await assert.rejects(readCitationStream(body(prefix + event('done', { complete: false })), () => {}, new AbortController().signal), /interrupted/)
})
test('malformed events and cancellation release stream readers', async () => {
  await assert.rejects(readCitationStream(body('event: sources\ndata: broken\n\n'), () => {}, new AbortController().signal), /invalid answer event/)
  const controller = new AbortController(); controller.abort()
  const stream = body(event('sources', { sources: [] }))
  await assert.rejects(readCitationStream(stream, () => {}, controller.signal), { name: 'AbortError' })
  assert.equal(stream.locked, false)
})

test('non-SSE bodies, HTTP 404/422 and API rejections never render garbage or fall back', async () => {
  const { requestCitationStream } = await import('../src/lib/sse-stream.js')
  for (const response of [new Response('Plain answer'), new Response('{}', { status: 404 }), new Response('{}', { status: 422 }), new Response('answer', { headers: { 'Content-Type': 'text/event-streaming' } })]) {
    const updates = []; let calls = 0
    await assert.rejects(requestCitationStream(async (path, options) => {
      calls++
      assert.equal(path, '/files/42/ask/stream?format=sse')
      assert.equal(options.method, 'POST')
      return response
    }, 42, 'token', 'Question', u => updates.push(u), new AbortController().signal), /does not support structured citation streaming/)
    assert.equal(calls, 1); assert.deepEqual(updates, [])
    assert.equal(response.body.locked, false)
  }
  for (const status of [404, 422]) {
    await assert.rejects(requestCitationStream(async () => { throw Object.assign(new Error('Failed'), { status }) }, 42, '', 'Q', () => {}, new AbortController().signal), new RegExp(`HTTP ${status}`))
  }
})

test('missing sources and token-before-sources fail without showing text', async () => {
  const updates = []
  for (const text of ['plain answer', event('token', { text: 'garbage' }), event('done', { complete: true })]) {
    await assert.rejects(readCitationStream(body(text), u => updates.push(u), new AbortController().signal), /does not support structured citation streaming/)
  }
  assert.deepEqual(updates, [])
})

test('open streams missing sources/done time out, cancel readers, and ignore keep-alives', async () => {
  for (const prefix of ['', event('sources', { sources: [] }) + event('token', { text: 'Partial' })]) {
    let cancelled = false; let interval
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(prefix))
        interval = setInterval(() => controller.enqueue(new TextEncoder().encode(': keep-alive\n\n')), 2)
      },
      cancel() { cancelled = true; clearInterval(interval) },
    })
    await assert.rejects(readCitationStream(stream, () => {}, new AbortController().signal,
      { sourcesTimeoutMs: 15, idleTimeoutMs: 15, totalTimeoutMs: 50 }), /streaming|timed out/)
    assert.equal(cancelled, true); assert.equal(stream.locked, false)
  }
})

test('an error event without done fails immediately rather than waiting indefinitely', async () => {
  let cancelled = false
  const stream = new ReadableStream({ start(c) { c.enqueue(new TextEncoder().encode(event('error', { message: 'Service unavailable' }))) }, cancel() { cancelled = true } })
  await assert.rejects(readCitationStream(stream, () => {}, new AbortController().signal), /Service unavailable/)
  assert.equal(cancelled, true)
})

test('the request helper preserves authenticated SSE success', async () => {
  const { requestCitationStream } = await import('../src/lib/sse-stream.js')
  const signal = new AbortController().signal
  const updates = []
  const result = await requestCitationStream(async (_, options) => {
    assert.equal(options.signal, signal)
    assert.equal(options.headers.Authorization, 'Bearer session-token')
    assert.deepEqual(JSON.parse(options.body), { question: 'Q', top_k: 3 })
    return new Response(body(event('sources', { sources: [] }) + event('token', { text: 'Answer' }) + event('done', { complete: true })), { headers: { 'Content-Type': 'text/event-stream; charset=utf-8' } })
  }, 1, 'session-token', 'Q', u => updates.push(u), signal)
  assert.equal(result.answer, 'Answer')
  assert.equal(updates[0].sources.length, 0)
})
