import { useEffect, useRef, useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ArrowDown, ArrowUp, MessageSquare, RotateCcw, Square, Copy, Check, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'

function CodeBlock({ children }) {
  const [copyState, setCopyState] = useState('idle')
  const timer = useRef(null)
  const code = useRef(null)
  useEffect(() => () => clearTimeout(timer.current), [])
  async function copy() {
    try {
      await navigator.clipboard.writeText(code.current?.textContent || '')
      setCopyState('copied')
    } catch { setCopyState('error') }
    clearTimeout(timer.current)
    timer.current = setTimeout(() => setCopyState('idle'), 2000)
  }
  return <div className="relative my-4 rounded-xl border bg-muted">
    <div className="flex justify-end border-b px-2 py-1"><Button variant="ghost" size="sm" onClick={copy} aria-label="Copy code">{copyState === 'copied' ? <Check /> : <Copy />}{copyState === 'copied' ? 'Copied' : 'Copy code'}</Button></div>
    {copyState === 'error' && <p role="alert" className="px-3 py-1 text-xs text-muted-foreground">Could not copy. Select the code to copy it manually.</p>}
    <pre ref={code} className="m-0! border-0!">{children}</pre>
  </div>
}

const markdownComponents = {
  pre: CodeBlock,
  a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
  img: ({ alt }) => <span>{alt || 'Image'}</span>,
}

export function ChatPanel({ turns, question, onQuestionChange, onAsk, onRetry, onStop, generating, loading, documentId, message, onClear, storageWarning, children }) {
  const scroll = useRef(null)
  const textarea = useRef(null)
  const nearBottom = useRef(true)
  const [showLatest, setShowLatest] = useState(false)
  const latest = turns.at(-1)

  useEffect(() => {
    const element = textarea.current
    if (!element) return
    element.style.height = 'auto'
    element.style.height = `${Math.min(element.scrollHeight, 160)}px`
  }, [question])

  useEffect(() => {
    if (nearBottom.current && scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight
  }, [turns])

  function jumpToLatest() {
    nearBottom.current = true
    setShowLatest(false)
    scroll.current.scrollTop = scroll.current.scrollHeight
  }

  function submit(event) {
    event.preventDefault()
    if (generating || loading || !documentId || !question.trim()) return
    nearBottom.current = true
    setShowLatest(false)
    onAsk(event)
    textarea.current?.focus()
  }

  return (
    <section className="relative flex h-full min-h-0 flex-col" aria-label="Document chat">
      <div className="flex h-14 shrink-0 items-center gap-2 border-b px-5 text-sm"><MessageSquare className="size-4 text-muted-foreground" aria-hidden="true" />Ask your PDF<Button className="ml-auto" size="sm" variant="ghost" disabled={!turns.length || generating || loading} onClick={onClear}><Trash2 />Clear chat</Button></div>
      <div ref={scroll} className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-8" onScroll={() => {
        const element = scroll.current
        nearBottom.current = element.scrollHeight - element.scrollTop - element.clientHeight < 80
        setShowLatest(!nearBottom.current)
      }}>
        <div className="mx-auto max-w-[720px] space-y-8">
          {!turns.length ? children : turns.map(turn => (
            <div key={turn.id} className="fade-in space-y-6">
              <article aria-label="Your message" className="ml-auto w-fit max-w-[80%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-secondary px-4 py-3 text-sm leading-6">{turn.question}</article>
              <article aria-label="AI answer" aria-busy={turn.status === 'streaming'} className="min-w-0 text-sm leading-7">
                {turn.answer ? <div className="chat-markdown"><Markdown remarkPlugins={[remarkGfm]} components={markdownComponents} skipHtml>{turn.answer}</Markdown></div>
                  : turn.status === 'streaming' ? <p className="flex items-center gap-2 text-muted-foreground"><span className="waiting-dot size-1.5 rounded-full bg-primary" aria-hidden="true" />Searching document...</p> : null}
                {(turn.status === 'error' || turn.status === 'stopped') && <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                  <p role={turn.status === 'error' ? 'alert' : undefined}>{turn.error || 'Answer stopped.'}</p>
                  {<Button size="sm" variant="ghost" disabled={generating || loading} onClick={() => { nearBottom.current = true; onRetry(turn) }}><RotateCcw className="size-3" />Retry answer</Button>}
                </div>}
              </article>
            </div>
          ))}
        </div>
      </div>
      {showLatest && <div className="absolute bottom-36 left-1/2 -translate-x-1/2"><Button variant="outline" size="sm" className="rounded-full bg-card shadow-sm" onClick={jumpToLatest}><ArrowDown />Latest message</Button></div>}
      <div className="sticky bottom-0 z-10 shrink-0 bg-background/95 px-4 pb-4 pt-2">
        <form onSubmit={submit} className="mx-auto flex max-w-[720px] items-end gap-2 rounded-xl border bg-card p-2 shadow-sm">
          <label htmlFor="pdf-question" className="sr-only">Question about your PDF</label>
          <textarea ref={textarea} id="pdf-question" rows={1} className="min-h-12 flex-1 resize-none overflow-y-auto border-0 bg-transparent px-3 py-3 text-sm focus-visible:outline-none" placeholder="Ask your PDF…" value={question} onChange={event => onQuestionChange(event.target.value)} disabled={!documentId || loading || generating} onKeyDown={event => {
            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && event.nativeEvent.keyCode !== 229) submit(event)
          }} />
          {generating ? <Button type="button" size="icon" className="rounded-lg" onClick={onStop} aria-label="Stop generating"><Square className="size-4" /></Button>
            : <Button type="submit" size="icon" className="rounded-lg" disabled={loading || !documentId || !question.trim()} aria-label="Send question"><ArrowUp className="size-4" /></Button>}
        </form>
        {storageWarning && <p role="alert" className="mx-auto mb-2 max-w-[720px] text-xs text-muted-foreground">{storageWarning}</p>}
        <p role="status" aria-live="polite" className="mx-auto mt-2 min-h-4 max-w-[720px] text-center text-xs text-muted-foreground">{generating ? latest?.answer ? 'Generating answer…' : 'Searching document...'  : message || (latest?.status === 'complete' ? 'Answer complete · Enter to send, Shift+Enter for a new line' : 'Enter to send · Shift+Enter for a new line')}</p>
      </div>
    </section>
  )
}
