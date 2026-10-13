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
          error: typeof turn.error === 'string' ? turn.error : '',
          ...(Array.isArray(turn.sources) ? { sources: normalizeSources(turn.sources) } : {}) }))
      } catch { warning = 'Some saved chat history could not be read. You can continue chatting.' }
    }
  } catch { warning = STORAGE_WARNING }
  return { history, warning }
}

export function saveHistories(storage, scope, history) {
  if (!scope) return ''
  try {
    for (const [id, turns] of Object.entries(history)) storage.setItem(`${PREFIX}${scope}:${id}`, JSON.stringify(turns))
    return ''
  } catch { return STORAGE_WARNING }
}
