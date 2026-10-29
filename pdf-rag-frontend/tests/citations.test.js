import test from 'node:test'
import assert from 'node:assert/strict'
import { citationPlugin } from '../src/lib/citation-markdown.js'
import { normalizeSources, citedSources, uniqueCitedPages, passageRange } from '../src/lib/citations.js'
import { loadHistories, saveHistories } from '../src/lib/chat-storage.js'
const sources = [
  { chunk_index: 25, page: 7, text: 'Café passage', preview: 'Preview', similarity: .8 },
  { chunk_index: 26, page: 7, text: 'Second passage' },
  { chunk_index: 27, page: null, preview: 'Old source' },
]
test('markers match chunk_index; pages are deduplicated and unknowns stay plain', () => {
  assert.equal(citedSources('[Chunk 25] [Chunk 25] [Chunk 27] [Chunk 999]', sources).length, 2)
  assert.equal(uniqueCitedPages('[Chunk 25] [Chunk 26] [Chunk 27]', sources).length, 1)
  const tree = { type: 'root', children: [{ type: 'paragraph', children: [{ type: 'text', value: 'See [Chunk 25] and [Chunk 999].' }, { type: 'inlineCode', value: '[Chunk 25]' }] }] }
  citationPlugin({ sources })(tree)
  assert.equal(tree.children[0].children[1].url, 'citation:25')
  assert.equal(tree.children[0].children[2].value, ' and [Chunk 999].')
  assert.equal(tree.children[0].children[3].type, 'inlineCode')
})
test('source validation and Unicode/spacing normalization preserve safe page matching', () => {
  assert.deepEqual(normalizeSources([{ chunk_index: 25, page: 0 }, ...sources]).map(s => s.page), [null, 7, null])
  assert.deepEqual(passageRange('Before Cafe\u0301  passage after', 'Café\npassage'), { start: 6, end: 17 })
  assert.equal(passageRange('Not present', 'Different text'), null)
})
test('localStorage preserves sources without changing old source-less messages', () => {
  const data = new Map()
  const storage = { get length() { return data.size }, key: i => [...data.keys()][i], getItem: key => data.get(key), setItem: (key, value) => data.set(key, value) }
  const legacy = { id: 'old', question: 'Old question', answer: '[Chunk 25]', status: 'complete', error: '' }
  saveHistories(storage, 'user', { 1: [legacy, { ...legacy, id: 'new', sources }] })
  const saved = loadHistories(storage, 'user').history[1]
  assert.equal('sources' in saved[0], false)
  assert.equal(saved[1].sources[0].page, 7)
  assert.equal(saved[1].sources[2].page, null)
})

test('full-width Chunk markers and non-breaking spaces still require a matching source', () => {
  const text = 'See 【Chunk\u00a027】 and [Chunk 25] and 【Chunk 999】.'
  assert.deepEqual(citedSources(text, sources).map(s => s.chunk_index), [27, 25])
  const tree = { type: 'root', children: [{ type: 'text', value: text }] }
  citationPlugin({ sources })(tree)
  assert.ok(tree.children.some(n => n.url === 'citation:27'))
  assert.ok(tree.children.some(n => n.type === 'text' && n.value.includes('【Chunk 999】')))
  const legacy = { type: 'root', children: [{ type: 'text', value: text }] }
  citationPlugin()(legacy)
  assert.equal(legacy.children[0].value, text)
})
