export function normalizeSources(value) {
  if (!Array.isArray(value)) return []
  const seen = new Set()
  return value.filter(source => source && Number.isInteger(source.chunk_index) && source.chunk_index >= 0 && !seen.has(source.chunk_index) && seen.add(source.chunk_index))
    .map(source => ({ chunk_index: source.chunk_index,
      page: Number.isInteger(source.page) && source.page >= 1 ? source.page : null,
      text: typeof source.text === 'string' ? source.text : '',
      preview: typeof source.preview === 'string' ? source.preview : '',
      similarity: typeof source.similarity === 'number' ? source.similarity : null }))
}

export function citedSources(answer, sources) {
  const byIndex = new Map(normalizeSources(sources).map(source => [source.chunk_index, source]))
  const seen = new Set()
  return [...answer.matchAll(/\[Chunk (\d+)\]/g)].map(match => Number(match[1]))
    .filter(index => byIndex.has(index) && !seen.has(index) && seen.add(index)).map(index => byIndex.get(index))
}

export function uniqueCitedPages(answer, sources) {
  const pages = new Map()
  for (const source of citedSources(answer, sources)) if (source.page && !pages.has(source.page)) pages.set(source.page, source)
  return [...pages.values()]
}

export function normalizePassage(text) {
  return text.normalize('NFKC').replace(/\u00ad/g, '').replace(/-\s*\n\s*/g, '').replace(/\s+/g, '').toLowerCase()
}

export function passageRange(pageText, passage) {
  const normalized = normalizePassage(passage)
  if (!normalized) return null
  const text = normalizePassage(pageText)
  const start = text.indexOf(normalized)
  return start < 0 ? null : { start, end: start + normalized.length }
}
