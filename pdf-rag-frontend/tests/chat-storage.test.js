import test from 'node:test'
import assert from 'node:assert/strict'
import { loadHistories, saveHistories, STORAGE_WARNING } from '../src/lib/chat-storage.js'
function memoryStorage() {
  const data = new Map()
  return { get length() { return data.size }, key: i => [...data.keys()][i], getItem: key => data.get(key), setItem: (key, value) => data.set(key, value) }
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
