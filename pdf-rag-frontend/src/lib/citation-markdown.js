import { chunkMarkerPattern, markerChunkIndex } from './citations.js'
export function citationPlugin({ sources = [] } = {}) {
  const indexes = new Set(sources.map(source => source.chunk_index))
  return tree => {
    function walk(node) {
      if (!node.children || ['link', 'linkReference', 'code', 'inlineCode'].includes(node.type)) return
      const children = []
      for (const child of node.children) {
        if (child.type !== 'text') { walk(child); children.push(child); continue }
        let start = 0
        for (const match of child.value.matchAll(chunkMarkerPattern())) {
          const index = markerChunkIndex(match)
          if (!indexes.has(index)) continue
          if (match.index > start) children.push({ type: 'text', value: child.value.slice(start, match.index) })
          children.push({ type: 'link', url: `citation:${index}`, children: [{ type: 'text', value: String(index) }] })
          start = match.index + match[0].length
        }
        if (start < child.value.length) children.push({ type: 'text', value: child.value.slice(start) })
      }
      node.children = children
    }
    walk(tree)
  }
}
