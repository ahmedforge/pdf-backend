import test from 'node:test'
import assert from 'node:assert/strict'
import { chatReducer, readAnswerStream } from '../src/lib/chat-state.js'

test('PDF histories remain isolated and stale stream updates cannot change a retried turn', () => {
  let state = chatReducer({}, { type: 'start', documentId: 1, id: 'old', question: 'First' })
  state = chatReducer(state, { type: 'start', documentId: 2, id: 'other', question: 'Other PDF' })
  state = chatReducer(state, { type: 'update', documentId: 1, id: 'old', update: { answer: 'Partial', status: 'error' } })
  state = chatReducer(state, { type: 'start', documentId: 1, id: 'retry', question: 'First', retryId: 'old' })
  state = chatReducer(state, { type: 'update', documentId: 1, id: 'old', update: { answer: 'Late response' } })
  assert.equal(state[1].length, 1)
  assert.equal(state[1][0].answer, '')
  assert.equal(state[2][0].question, 'Other PDF')
  assert.deepEqual(chatReducer(state, { type: 'reset' }), {})
})

test('stream decodes split UTF-8 characters and preserves Markdown chunks', async () => {
  const expected = '## Café ☕\n\n**Useful** answer'
  const bytes = new TextEncoder().encode(expected)
  const body = new ReadableStream({ start(controller) {
    for (const byte of bytes) controller.enqueue(new Uint8Array([byte]))
    controller.close()
  } })
  const updates = []
  assert.equal(await readAnswerStream(body, text => updates.push(text), new AbortController().signal), expected)
  assert.equal(updates.at(-1), expected)
})

test('empty streams fail and stopped streams release the reader', async () => {
  await assert.rejects(readAnswerStream(new ReadableStream({ start(c) { c.close() } }), () => {}, new AbortController().signal), /No answer/)
  const controller = new AbortController()
  controller.abort()
  let canceled = false
  const body = new ReadableStream({ cancel() { canceled = true } })
  await assert.rejects(readAnswerStream(body, () => {}, controller.signal), { name: 'AbortError' })
  assert.equal(canceled, true)
  assert.equal(body.locked, false)
})

test('full responses are progressively revealed and pending reads can be stopped', async () => {
  const text = 'A complete answer with enough text to show the typing fallback.'
  const full = new ReadableStream({ start(c) { c.enqueue(new TextEncoder().encode(text)); c.close() } })
  const updates = []
  assert.equal(await readAnswerStream(full, value => updates.push(value), new AbortController().signal), text)
  assert.ok(updates.length > 1)
  assert.ok(updates[0].length < text.length)
  const controller = new AbortController()
  const pending = new ReadableStream({ start(c) { c.enqueue(new TextEncoder().encode('Partial')) } })
  const result = readAnswerStream(pending, () => controller.abort(), controller.signal)
  await assert.rejects(result, { name: 'AbortError' })
})
