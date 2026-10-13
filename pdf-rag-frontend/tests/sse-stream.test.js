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
