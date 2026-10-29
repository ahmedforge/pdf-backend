import test from 'node:test'
import assert from 'node:assert/strict'
import { loadHistories, saveHistories, STORAGE_WARNING } from '../src/lib/chat-storage.js'
function memoryStorage() {
  const data = new Map()
  return { get length() { return data.size }, key: i => [...data.keys()][i], getItem: key => data.get(key), setItem: (key, value) => data.set(key, value), removeItem: key => data.delete(key) }
}
const turn = { id: 'one', question: 'Hello', answer: 'World', status: 'complete', error: '' }
test('history survives reload, isolates accounts and clears one PDF only', () => {
  const storage = memoryStorage()
  saveHistories(storage, 'alice', { 1: [turn], 2: [turn] })
  saveHistories(storage, 'bob', { 1: [{ ...turn, answer: 'Bob' }] })
  saveHistories(storage, 'alice', { 1: [] })
  assert.deepEqual(loadHistories(storage, 'alice').history[1], [])
  assert.equal(loadHistories(storage, 'alice').history[2][0].answer, 'World')
  assert.equal(loadHistories(storage, 'bob').history[1][0].answer, 'Bob')
})
test('corrupt, blocked and quota-limited storage are safe; interrupted answers restore stopped', () => {
  const storage = memoryStorage()
  storage.setItem('pdf-rag-chat:v1:alice:1', '{broken')
  saveHistories(storage, 'alice', { 2: [{ ...turn, status: 'streaming' }] })
  const result = loadHistories(storage, 'alice')
  assert.ok(result.warning)
  assert.equal(result.history[2][0].status, 'stopped')
  assert.equal(saveHistories({ setItem() { throw new Error('Quota') } }, 'alice', { 2: [turn] }), STORAGE_WARNING)
  assert.equal(loadHistories({ get length() { throw new Error('Blocked') } }, 'alice').warning, STORAGE_WARNING)
})

test('stored sources contain only citation fields and a 300-character snippet', () => {
  const storage = memoryStorage()
  saveHistories(storage, 'alice', { 1: [{ ...turn, sources: [{ chunk_index: 25, page: 7, similarity: .9, text: 'x'.repeat(5000), preview: 'duplicate', chunk_id: 123 }] }] })
  const source = JSON.parse(storage.getItem('pdf-rag-chat:v1:alice:1'))[0].sources[0]
  assert.deepEqual(Object.keys(source).sort(), ['chunk_index', 'page', 'similarity', 'text'])
  assert.equal(source.text.length, 300)
})

test('quota recovery evicts oldest stored sources, keeps text/accounts, and retries once', () => {
  const storage = memoryStorage()
  const sourced = (id, createdAt) => ({ ...turn, id, createdAt, sources: [{ chunk_index: 1, page: 1, text: 'citation' }] })
  saveHistories(storage, 'alice', { 1: [sourced('older', 1)], 2: [sourced('later', 2)] })
  saveHistories(storage, 'bob', { 1: [sourced('bob', 1)] })
  const writes = []; const original = storage.setItem
  let attempts = 0
  storage.setItem = (key, value) => {
    writes.push(key)
    if (key.endsWith('alice:3') && ++attempts === 1) throw new DOMException('Full', 'QuotaExceededError')
    original(key, value)
  }
  assert.equal(saveHistories(storage, 'alice', { 3: [sourced('new', 3)] }), '')
  assert.equal(attempts, 2)
  assert.deepEqual(writes.slice(1, 3), ['pdf-rag-chat:v1:alice:1', 'pdf-rag-chat:v1:alice:2'])
  const loaded = loadHistories(storage, 'alice').history
  for (const turns of Object.values(loaded)) {
    assert.equal(turns[0].question, 'Hello'); assert.equal(turns[0].answer, 'World')
    assert.equal(turns[0].sources, undefined)
  }
  assert.equal(loadHistories(storage, 'bob').history[1][0].sources.length, 1)
})

test('a failed quota retry is safe and is not repeated', () => {
  let writes = 0
  const storage = { length: 0, setItem() { writes++; throw new DOMException('Full', 'QuotaExceededError') } }
  assert.equal(saveHistories(storage, 'alice', { 1: [turn] }), STORAGE_WARNING)
  assert.equal(writes, 2)
})

test('corrupt JSON and invalid records return an empty history for that document', () => {
  const storage = memoryStorage()
  storage.setItem('pdf-rag-chat:v1:alice:1', '{broken')
  storage.setItem('pdf-rag-chat:v1:alice:2', '[{"id":"bad"}]')
  const result = loadHistories(storage, 'alice')
  assert.deepEqual(result.history, { 1: [], 2: [] })
  assert.ok(result.warning)
})

test('a shared source budget evicts older citations across PDFs while retaining all messages', () => {
  const storage = memoryStorage()
  const sources = Array.from({ length: 20 }, (_, chunk_index) => ({ chunk_index, page: 1, text: 'x'.repeat(300) }))
  const turns = Array.from({ length: 10 }, (_, i) => ({ ...turn, id: String(i), createdAt: i + 1, sources }))
  saveHistories(storage, 'alice', { 1: turns.slice(0, 5), 2: turns.slice(5) })
  const loaded = loadHistories(storage, 'alice').history
  assert.equal(loaded[1].length + loaded[2].length, 10)
  assert.equal(loaded[1][0].sources, undefined)
  assert.equal(loaded[2][4].sources.length, 20)
  const bytes = Object.values(loaded).flat().reduce((n, t) => n + (t.sources ? JSON.stringify(t.sources).length * 2 : 0), 0)
  assert.ok(bytes <= 64 * 1024)
})

test('blocked token storage cannot prevent login or logout', async () => {
  const { readToken, saveToken, removeToken } = await import('../src/lib/token-storage.js')
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, get() { throw new Error('Blocked') } })
  try {
    assert.equal(readToken(), '')
    assert.equal(saveToken('token'), false)
    assert.doesNotThrow(removeToken)
  } finally {
    if (descriptor) Object.defineProperty(globalThis, 'localStorage', descriptor)
    else delete globalThis.localStorage
  }
})

test('confirmed document removal deletes only its account-scoped saved history', async () => {
  const { removeHistory } = await import('../src/lib/chat-storage.js')
  const storage = memoryStorage()
  saveHistories(storage, 'alice', { 1: [turn], 2: [turn] })
  saveHistories(storage, 'bob', { 1: [turn] })
  assert.equal(removeHistory(storage, 'alice', 1), '')
  assert.equal(storage.getItem('pdf-rag-chat:v1:alice:1'), undefined)
  assert.equal(loadHistories(storage, 'alice').warning, '')
  assert.equal(loadHistories(storage, 'alice').history[2][0].answer, 'World')
  assert.equal(loadHistories(storage, 'bob').history[1][0].answer, 'World')
  assert.equal(removeHistory({ removeItem() { throw new Error('Blocked') } }, 'alice', 1), STORAGE_WARNING)
})
