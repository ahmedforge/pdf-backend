export function citationPlugin({ sources = [] } = {}) {
  const indexes = new Set(sources.map(source => source.chunk_index))
  return tree => {
    function walk(node) {
      if (!node.children || ['link', 'linkReference', 'code', 'inlineCode'].includes(node.type)) return
      const children = []
      for (const child of node.children) {
        if (child.type !== 'text') { walk(child); children.push(child); continue }
        let start = 0
        for (const match of child.value.matchAll(/\[Chunk (\d+)\]/g)) {
          if (!indexes.has(Number(match[1]))) continue
          if (match.index > start) children.push({ type: 'text', value: child.value.slice(start, match.index) })
          children.push({ type: 'link', url: `citation:${Number(match[1])}`, children: [{ type: 'text', value: match[1] }] })
          start = match.index + match[0].length
        }
        if (start < child.value.length) children.push({ type: 'text', value: child.value.slice(start) })
      }
      node.children = children
    }
    walk(tree)
  }
}
