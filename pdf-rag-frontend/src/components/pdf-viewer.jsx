import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import { useVirtualizer } from '@tanstack/react-virtual'
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut, ScanLine, FileText } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { apiRequest } from '@/api'
import { normalizePassage, passageRange } from '@/lib/citations'
import 'react-pdf/dist/Page/TextLayer.css'
import 'react-pdf/dist/Page/AnnotationLayer.css'

const PDF_OPTIONS = {
  cMapUrl: `${import.meta.env.BASE_URL}pdfjs/cmaps/`, cMapPacked: true,
  standardFontDataUrl: `${import.meta.env.BASE_URL}pdfjs/standard_fonts/`,
  wasmUrl: `${import.meta.env.BASE_URL}pdfjs/wasm/`,
  iccUrl: `${import.meta.env.BASE_URL}pdfjs/iccs/`,
}

pdfjs.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString()

function CitationPage({ pageNumber, width, citation, highlights }) {
  const root = useRef(null)
  const ready = useRef(false)
  const clearTimer = useRef(null)
  const highlight = useCallback(() => {
    const element = root.current
    if (!element || !ready.current || !citation || citation.page !== pageNumber) return
    const existingExpiry = highlights.current.get(citation.key)
    if (existingExpiry && existingExpiry <= Date.now()) return
    const expiry = existingExpiry || Date.now() + 1800
    highlights.current.set(citation.key, expiry)
    clearTimeout(clearTimer.current)
    element.querySelectorAll('.citation-hit').forEach(span => span.classList.remove('citation-hit'))
    element.classList.remove('citation-page-pulse')
    const spans = [...element.querySelectorAll('.react-pdf__Page__textContent span')].filter(span => !span.querySelector('span'))
    const pieces = spans.map(span => normalizePassage(span.textContent || ''))
    const match = passageRange(pieces.join(''), citation.text || citation.preview || '')
    let offset = 0
    if (match) spans.forEach((span, index) => {
      const end = offset + pieces[index].length
      if (end > match.start && offset < match.end) span.classList.add('citation-hit')
      offset = end
    })
    else {
      // Restart the fade pulse when the same source is clicked again.
      void element.offsetWidth
      element.classList.add('citation-page-pulse')
    }
    clearTimer.current = setTimeout(() => {
      element.querySelectorAll('.citation-hit').forEach(span => span.classList.remove('citation-hit'))
      element.classList.remove('citation-page-pulse')
    }, Math.max(0, expiry - Date.now()))
  }, [citation, pageNumber, highlights])
  useEffect(() => { highlight(); return () => clearTimeout(clearTimer.current) }, [highlight])
  return <div ref={root} className="citation-page relative mx-auto w-fit bg-white shadow-sm">
    <Page pageNumber={pageNumber} width={width} suspense={false} renderAnnotationLayer={false}
      devicePixelRatio={Math.min(window.devicePixelRatio || 1, 2)}
      onRenderTextLayerSuccess={() => { ready.current = true; highlight() }}
      onRenderTextLayerError={() => { ready.current = true; highlight() }}
      loading={<p className="p-4 text-xs text-gray-600">Rendering page {pageNumber}…</p>}
      error={<p role="alert" className="p-4 text-xs text-gray-600">Could not render page {pageNumber}.</p>} />
  </div>
}

function LoadedPdf({ file, filename, currentPage, onPageChange, navigation }) {
  const scroll = useRef(null)
  const [size, setSize] = useState({ width: 500, height: 600 })
  const [numPages, setNumPages] = useState(0)
  const [ratio, setRatio] = useState(1.414)
  const [zoom, setZoom] = useState(1)
  const [pageDraft, setPageDraft] = useState(null)
  const pageInput = pageDraft ?? String(currentPage)
  const [notice, setNotice] = useState('')
  const [loadError, setLoadError] = useState('')
  const jump = useRef(null)
  const lastNavigation = useRef(null)
  const highlights = useRef(new Map())
  const restored = useRef(false)
  const width = Math.max(160, (size.width - 32) * zoom)
  const estimateSize = useCallback(() => width * ratio + 24, [width, ratio])
  // eslint-disable-next-line react-hooks/incompatible-library -- Mutable virtualizer methods are intentionally not compiler-memoized.
  const virtualizer = useVirtualizer({ count: numPages, getScrollElement: () => scroll.current, estimateSize, overscan: 2, useAnimationFrameWithResizeObserver: true })
  const items = virtualizer.getVirtualItems()

  useEffect(() => {
    const element = scroll.current
    if (!element) return
    let frame
    const observer = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => setSize(old => old.width === width && old.height === height ? old : { width, height }))
    })
    observer.observe(element)
    return () => { observer.disconnect(); cancelAnimationFrame(frame) }
  }, [])

  useEffect(() => {
    virtualizer.measure()
  }, [width, ratio, virtualizer])

  const goTo = useCallback(page => {
    if (!Number.isInteger(page) || page < 1 || page > numPages) {
      setNotice(`Enter a page from 1 to ${numPages}.`)
      return
    }
    setNotice('')
    onPageChange(page)
    jump.current = { page, until: Date.now() + 1500 }
    virtualizer.scrollToIndex(page - 1, { align: 'start', behavior: 'auto' })
  }, [numPages, onPageChange, virtualizer])

  useEffect(() => {
    if (!numPages) return
    const isNewCitation = navigation && lastNavigation.current !== navigation.key
    if (!isNewCitation && restored.current) return
    const target = isNewCitation ? navigation.page : Math.min(currentPage, numPages)
    const timer = setTimeout(() => {
      restored.current = true
      if (isNewCitation) lastNavigation.current = navigation.key
      goTo(target)
    }, 0)
    return () => clearTimeout(timer)
  }, [navigation, numPages, goTo, currentPage])

  // Keep a remote jump on target as real heights replace estimates.
  useEffect(() => {
    const target = jump.current
    if (!target || Date.now() > target.until) return
    const timer = setTimeout(() => virtualizer.scrollToIndex(target.page - 1, { align: 'start', behavior: 'auto' }), 50)
    return () => clearTimeout(timer)
  }, [items, virtualizer])

  const loaded = useCallback(async pdf => {
    setNumPages(pdf.numPages)
    try {
      const page = await pdf.getPage(1)
      const viewport = page.getViewport({ scale: 1 })
      setRatio(viewport.height / viewport.width)
    } catch { /* Default ratio handles first-page metadata failures. */ }
  }, [])
  const toolbarDisabled = !numPages || !!loadError
  const citation = useMemo(() => navigation?.source ? { ...navigation.source, key: navigation.key, createdAt: navigation.createdAt } : null, [navigation])
  return <section className="flex h-full min-h-0 flex-col bg-muted/40" aria-label="PDF preview">
    <div className="flex shrink-0 flex-wrap items-center gap-1 border-b bg-background p-2 text-xs">
      <span className="sr-only">{filename}</span>
      <Button variant="ghost" size="icon-sm" disabled={toolbarDisabled || currentPage <= 1} aria-label="Previous page" onClick={() => goTo(currentPage - 1)}><ChevronLeft /></Button>
      <form className="flex items-center gap-1" onSubmit={event => { event.preventDefault(); goTo(Number(pageInput)); setPageDraft(null) }}>
        <label htmlFor="pdf-page" className="sr-only">PDF page number</label>
        <input id="pdf-page" aria-label="PDF page number" className="h-8 w-12 px-1 text-center text-xs" inputMode="numeric" value={pageInput} disabled={toolbarDisabled} onChange={event => setPageDraft(event.target.value)} onBlur={() => { if (pageInput !== String(currentPage)) goTo(Number(pageInput)); setPageDraft(null) }} />
        <span aria-label="Total pages">/ {numPages || '—'}</span>
      </form>
      <Button variant="ghost" size="icon-sm" disabled={toolbarDisabled || currentPage >= numPages} aria-label="Next page" onClick={() => goTo(currentPage + 1)}><ChevronRight /></Button>
      <div className="ml-auto flex items-center gap-1">
        <Button variant="ghost" size="icon-sm" disabled={toolbarDisabled || zoom <= .5} aria-label="Zoom out" onClick={() => setZoom(value => Math.max(.5, value - .25))}><ZoomOut /></Button>
        <span className="min-w-9 text-center">{Math.round(zoom * 100)}%</span>
        <Button variant="ghost" size="icon-sm" disabled={toolbarDisabled || zoom >= 2.5} aria-label="Zoom in" onClick={() => setZoom(value => Math.min(2.5, value + .25))}><ZoomIn /></Button>
        <Button variant="ghost" size="icon-sm" disabled={toolbarDisabled} aria-label="Fit width" onClick={() => setZoom(1)}><ScanLine /></Button>
      </div>
    </div>
    {notice && <p role="alert" className="px-3 py-1 text-xs text-muted-foreground">{notice}</p>}
    <div ref={scroll} className="min-h-0 flex-1 overflow-auto overscroll-contain [scrollbar-gutter:stable]" onWheel={() => { jump.current = null }} onTouchStart={() => { jump.current = null }} onScroll={() => {
      if (jump.current && Date.now() < jump.current.until) return
      const anchor = scroll.current.scrollTop + Math.min(100, size.height / 3)
      const visible = virtualizer.getVirtualItems().find(item => item.start <= anchor && item.end > anchor)
      if (visible) onPageChange(visible.index + 1)
    }}>
      <Document file={file} options={PDF_OPTIONS} suspense={false} onLoadSuccess={loaded} onLoadError={error => setLoadError(error.message)}
        loading={<p role="status" className="p-6 text-sm">Loading PDF…</p>}
        error={<p role="alert" className="p-6 text-sm">Could not open PDF: {loadError || 'Invalid or unsupported PDF.'}</p>}>
        <div className="relative" style={{ height: virtualizer.getTotalSize(), minWidth: width + 32 }}>
          {items.map(item => <div key={item.key} data-index={item.index} ref={virtualizer.measureElement}
            className="absolute top-0 left-0 w-full px-4 pt-3 pb-3" style={{ transform: `translateY(${item.start}px)` }}>
            <CitationPage pageNumber={item.index + 1} width={width} citation={citation?.page === item.index + 1 ? citation : null} highlights={highlights} />
          </div>)}
        </div>
      </Document>
    </div>
  </section>
}

export function PdfViewer({ documentId, token, filename, currentPage, onPageChange, navigation }) {
  const [result, setResult] = useState(null)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    if (!documentId) return
    const controller = new AbortController()
    let active = true
    let url
    apiRequest(`/download/${documentId}`, { headers: { Authorization: `Bearer ${token}` }, signal: controller.signal })
      .then(response => response.blob()).then(blob => {
        if (!active) return
        url = URL.createObjectURL(blob)
        setResult({ id: documentId, token, url, attempt })
      }).catch(error => { if (active && error.name !== 'AbortError') setResult({ id: documentId, token, error: error.message, attempt }) })
    return () => { active = false; controller.abort(); if (url) URL.revokeObjectURL(url) }
  }, [documentId, token, attempt])
  const file = useMemo(() => result?.url || null, [result])
  if (!documentId) return <div className="flex h-full flex-col items-center justify-center gap-3 bg-muted/40 text-muted-foreground"><FileText className="size-10 stroke-1" /><p className="text-sm">Your PDF will appear here.</p></div>
  if (result?.id !== documentId || result?.token !== token || result?.attempt !== attempt) return <p role="status" className="p-6 text-sm">Loading PDF…</p>
  if (result.error) return <div role="alert" className="p-6 text-sm"><p>Could not download PDF: {result.error}</p><Button variant="outline" size="sm" className="mt-3" onClick={() => setAttempt(value => value + 1)}>Retry PDF</Button></div>
  return <LoadedPdf key={`${documentId}:${attempt}`} file={file} filename={filename} currentPage={currentPage} onPageChange={onPageChange} navigation={navigation} />
}
