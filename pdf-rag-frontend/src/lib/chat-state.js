export function chatReducer(state, action) {
  if (action.type === 'reset') return {}
  if (action.type === 'hydrate') return action.history
  if (action.type === 'clear') return { ...state, [action.documentId]: [] }
  const turns = state[action.documentId] || []
  if (action.type === 'start') {
    const turn = { id: action.id, question: action.question, answer: '', status: 'streaming', error: '' }
    return { ...state, [action.documentId]: action.retryId
      ? turns.map(old => old.id === action.retryId ? turn : old)
      : [...turns, turn] }
  }
  return { ...state, [action.documentId]: turns.map(turn => turn.id === action.id
    ? { ...turn, ...action.update } : turn) }
}

export async function readAnswerStream(body, onText, signal) {
  if (!body) throw new Error('No answer stream was received')
  const reader = body.getReader()
  const decoder = new TextDecoder()
  const checkAbort = () => { if (signal.aborted) throw new DOMException('Stopped', 'AbortError') }
  const cancel = () => { reader.cancel().catch(() => {}) }
  signal.addEventListener('abort', cancel, { once: true })
  try {
    checkAbort()
    const first = await reader.read()
    checkAbort()
    if (first.done) throw new Error('No answer was received. Please retry.')
    let text = decoder.decode(first.value, { stream: true })
    const nextRead = reader.read()
    let timer
    const probe = await Promise.race([
      nextRead.then(result => ({ result })),
      new Promise(resolve => { timer = setTimeout(() => resolve({ waiting: true }), 16) }),
    ])
    clearTimeout(timer)
    checkAbort()
    if (probe.result?.done) {
      text += decoder.decode()
      if (!text.trim()) throw new Error('No answer was received. Please retry.')
      const characters = Array.from(text)
      const batch = Math.max(3, Math.ceil(characters.length / 80))
      for (let i = batch; i < characters.length; i += batch) {
        checkAbort()
        onText(characters.slice(0, i).join(''))
        await new Promise(resolve => setTimeout(resolve, 16))
      }
      checkAbort()
      onText(text)
    } else {
      onText(text)
      let item = probe.result || await nextRead
      while (!item.done) {
        checkAbort()
        text += decoder.decode(item.value, { stream: true })
        onText(text)
        item = await reader.read()
      }
      checkAbort()
      text += decoder.decode()
      onText(text)
    }
    if (!text.trim()) throw new Error('No answer was received. Please retry.')
    return text
  } finally {
    signal.removeEventListener('abort', cancel)
    try { await reader.cancel() } catch { /* Network may already be closed. */ }
    reader.releaseLock()
  }
}
