import { normalizeSources } from './citations.js'
const PREFIX = 'pdf-rag-chat:v1:'
export const STORAGE_WARNING = 'Chat history could not be saved on this device. Messages will remain available until you close or reload this page.'

export function historyScope(token) {
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    return payload.sub == null ? '' : encodeURIComponent(String(payload.sub))
  } catch { return '' }
}

export function loadHistories(storage, scope) {
  if (!scope) return { history: {}, warning: '' }
  const history = {}
  let warning = ''
  const prefix = `${PREFIX}${scope}:`
  try {
    for (let i = 0; i < storage.length; i++) {
      const key = storage.key(i)
      if (!key?.startsWith(prefix)) continue
      const id = key.slice(prefix.length)
      if (!/^\d+$/.test(id)) continue
      try {
        const data = JSON.parse(storage.getItem(key))
        if (!Array.isArray(data) || !data.every(turn => turn && typeof turn.id === 'string' && typeof turn.question === 'string' && typeof turn.answer === 'string' && ['streaming', 'complete', 'error', 'stopped'].includes(turn.status))) throw new Error('Invalid history')
        history[id] = data.map(turn => ({ id: turn.id, question: turn.question, answer: turn.answer,
          status: turn.status === 'streaming' ? 'stopped' : turn.status,
          createdAt: Number.isFinite(turn.createdAt) ? turn.createdAt : 0,
          error: typeof turn.error === 'string' ? turn.error : '',
          ...(Array.isArray(turn.sources) ? { sources: compactSources(turn.sources) } : {}) }))
      } catch { history[id] = []; warning = 'Some saved chat history could not be read. You can continue chatting.' }
    }
  } catch { warning = STORAGE_WARNING }
  return { history, warning }
}

// One shared budget per account; message text is never evicted.
export const SOURCE_BUDGET = 64 * 1024
function compactSources(sources) {
  return normalizeSources(sources).map(source => ({
    chunk_index: source.chunk_index, page: source.page, similarity: source.similarity,
    text: (source.text || source.preview).slice(0, 300),
  }))
}
export function saveHistories(storage, scope, history) {
  if (!scope) return ''
  try {
    const merged = { ...loadHistories(storage, scope).history, ...history }
    const changed = new Set(Object.keys(history))
    const candidates = []
    let size = 0
    for (const [id, turns] of Object.entries(merged)) {
      merged[id] = turns.map(turn => {
        const saved = { ...turn }
        if (Array.isArray(turn.sources)) saved.sources = compactSources(turn.sources)
        const bytes = saved.sources?.length ? JSON.stringify(saved.sources).length * 2 : 0
        size += bytes
        if (bytes) candidates.push({ id, turn: saved, bytes })
        return saved
      })
    }
    candidates.sort((a, b) => (a.turn.createdAt || 0) - (b.turn.createdAt || 0))
    for (const candidate of candidates) {
      if (size <= SOURCE_BUDGET) break
      delete candidate.turn.sources
      changed.add(candidate.id)
      size -= candidate.bytes
    }
    const write = () => {
      for (const id of changed) storage.setItem(`${PREFIX}${scope}:${id}`, JSON.stringify(merged[id]))
    }
    try { write() } catch (error) {
      if (error?.name !== 'QuotaExceededError') return STORAGE_WARNING
      // Free existing records in oldest-first order before retrying the save once.
      // Drop citation metadata only; leave all questions/answers intact.
      for (const candidate of candidates) {
        if (!candidate.turn.sources) continue
        delete candidate.turn.sources
        changed.add(candidate.id)
      }
      const existing = loadHistories(storage, scope).history
      const oldest = Object.entries(existing).sort((a, b) =>
        Math.min(...a[1].map(t => t.createdAt || 0)) - Math.min(...b[1].map(t => t.createdAt || 0)))
      for (const [id, turns] of oldest) {
        if (!turns.some(turn => turn.sources?.length)) continue
        storage.setItem(`${PREFIX}${scope}:${id}`, JSON.stringify(turns.map(turn => {
          const saved = { ...turn }; delete saved.sources; return saved
        })))
      }
      write()
    }
    return ''
  } catch { return STORAGE_WARNING }
}

export function removeHistory(storage, scope, id) {
  try { storage.removeItem(`${PREFIX}${scope}:${id}`); return '' }
  catch { return STORAGE_WARNING }
}
