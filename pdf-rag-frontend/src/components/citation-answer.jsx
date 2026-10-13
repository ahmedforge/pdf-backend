import Markdown, { defaultUrlTransform } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Tooltip } from 'radix-ui'
import { normalizeSources, citedSources, uniqueCitedPages } from '@/lib/citations'
import { citationPlugin } from '@/lib/citation-markdown'

function CitationChip({ source, onNavigate, currentPage, label }) {
  const snippet = (source.preview || source.text || 'No preview available.').slice(0, 220)
  return <Tooltip.Root>
    <Tooltip.Trigger asChild>
      <button type="button" data-slot="citation" aria-disabled={!source.page}
        aria-label={source.page ? `Source ${source.chunk_index}, page ${source.page}` : `Source ${source.chunk_index}, page unavailable`}
        aria-current={source.page && source.page === currentPage ? 'page' : undefined}
        className={`mx-0.5 inline-flex min-w-5 items-center justify-center rounded-md border px-1.5 align-baseline text-[11px] font-medium leading-5 ${source.page ? 'cursor-pointer bg-accent text-accent-foreground' : 'cursor-default bg-muted text-muted-foreground'}`}
        onClick={() => { if (source.page) onNavigate(source) }}>{label ?? source.chunk_index}</button>
    </Tooltip.Trigger>
    <Tooltip.Portal><Tooltip.Content sideOffset={6} className="fade-in z-50 max-w-xs rounded-xl border bg-popover px-3 py-2 text-xs leading-5 text-popover-foreground shadow-sm">
      {source.page && <p className="mb-1 font-medium">Page {source.page}</p>}<p>{snippet}</p><Tooltip.Arrow className="fill-popover" />
    </Tooltip.Content></Tooltip.Portal>
  </Tooltip.Root>
}

export function CitationAnswer({ answer, sources, onNavigate, currentPage, components }) {
  const normalized = normalizeSources(sources)
  const byIndex = new Map(normalized.map(source => [source.chunk_index, source]))
  const cited = citedSources(answer, normalized)
  const pages = uniqueCitedPages(answer, normalized)
  return <Tooltip.Provider delayDuration={200}>
    <div className="chat-markdown"><Markdown skipHtml remarkPlugins={[remarkGfm, [citationPlugin, { sources: normalized }]]}
      urlTransform={url => /^citation:\d+$/.test(url) && byIndex.has(Number(url.slice(9))) ? url : defaultUrlTransform(url)}
      components={{ ...components, a: props => {
        const source = props.href?.startsWith('citation:') && byIndex.get(Number(props.href.slice(9)))
        return source ? <CitationChip source={source} onNavigate={onNavigate} currentPage={currentPage} />
          : <a href={props.href} target="_blank" rel="noopener noreferrer">{props.children}</a>
      } }}>{answer}</Markdown></div>
    {cited.length > 0 && <div aria-label="Cited sources" className="mt-3 flex flex-wrap items-center gap-1 text-xs text-muted-foreground"><span className="mr-1">Sources</span>
      {pages.map(source => <CitationChip key={source.page} source={source} onNavigate={onNavigate} currentPage={currentPage} label={`p. ${source.page}`} />)}
      {cited.some(source => !source.page) && <span className="ml-1">{pages.length ? 'Some sources have no page metadata' : 'Page metadata unavailable'}</span>}
    </div>}
  </Tooltip.Provider>
}
