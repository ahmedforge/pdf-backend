import { lazy, Suspense, useCallback, useRef, useState, useSyncExternalStore } from "react"
import { LogOut, PanelLeftClose, PanelLeftOpen, Upload, MessageSquare } from "lucide-react"
const PdfViewer = lazy(() => import("@/components/pdf-viewer").then(module => ({ default: module.PdfViewer })))
import { Button } from "@/components/ui/button"
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ChatPanel } from "@/components/chat-panel"
import { UploadList } from "@/components/upload-list"
import { DocumentItem } from "@/components/document-item"
import { ThemeToggle } from "@/components/theme-toggle"

function subscribeMobile(callback) {
  const query = window.matchMedia("(max-width: 767px)")
  query.addEventListener("change", callback)
  return () => query.removeEventListener("change", callback)
}
const getMobileSnapshot = () => window.matchMedia("(max-width: 767px)").matches

const suggestions = ["Summarize this document", "What are the key takeaways?", "Explain the main ideas simply"]

export function WorkspaceShell({ token, files, documentId, onSelectDocument, onUpload, uploads, onRename, onDelete, onLogout, question, onQuestionChange, onAsk, turns, generating, onStop, onRetry, onClear, storageWarning, message, loading }) {
  const mobile = useSyncExternalStore(subscribeMobile, getMobileSnapshot, () => false)
  const [collapsed, setCollapsed] = useState(getMobileSnapshot)
  const [mobileTab, setMobileTab] = useState("chat")
  const [dragging, setDragging] = useState(false)
  const [pages, setPages] = useState({})
  const [navigation, setNavigation] = useState(null)
  const currentPage = pages[documentId] || 1
  const pageChanged = useCallback(page => {
    setPages(old => old[documentId] === page ? old : { ...old, [documentId]: page })
  }, [documentId])
  function cite(source) {
    if (!source.page) return
    setNavigation({ documentId, page: source.page, source, key: crypto.randomUUID(), createdAt: Date.now() })
    if (mobile) { setMobileTab('pdf'); setCollapsed(true) }
  }
  const input = useRef(null)
  const selected = files.find(file => file.id === documentId)

  function upload(files) { if (files?.length) { onUpload(files); setCollapsed(false) } }
  async function deleteDocument(id) {
    await onDelete(id)
    setPages(old => { const next = { ...old }; delete next[id]; return next })
    setNavigation(old => old?.documentId === id ? null : old)
  }

  const preview = <Suspense fallback={<p role="status" className="p-6 text-sm">Loading PDF viewer…</p>}><PdfViewer key={documentId || 'empty'} documentId={documentId} token={token} filename={selected?.filename}
    currentPage={currentPage} onPageChange={pageChanged} navigation={navigation?.documentId === documentId ? navigation : null} /></Suspense>
  const chat = (
    <ChatPanel key={documentId || 'empty'} documentId={documentId} turns={turns} question={question}
      onQuestionChange={onQuestionChange} onAsk={onAsk} onRetry={onRetry} onStop={onStop}
      generating={generating} loading={loading} message={message} onClear={onClear} storageWarning={storageWarning} currentPage={currentPage} onCitation={cite}>
            <div className="fade-in flex min-h-64 flex-col items-center justify-center gap-4 text-center">
              <div className="rounded-xl border bg-card p-3 shadow-xs"><MessageSquare className="size-5 text-primary" aria-hidden="true" /></div>
              <h2 className="m-0 text-xl font-medium">{documentId ? "A little clarity, one question at a time." : "Your next insight starts here."}</h2>
              <p className="max-w-sm text-sm text-muted-foreground">{documentId ? "Ask about your document or start with a suggestion." : "Drop your PDFs below and explore them, one question at a time."}</p>
              {!documentId ? (
                <div className={`w-full max-w-sm rounded-xl border border-dashed p-7 ${dragging ? "bg-accent" : "bg-card"}`}
                  onDragOver={event => { event.preventDefault(); setDragging(true) }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={event => { event.preventDefault(); setDragging(false); upload(event.dataTransfer.files) }}>
                  <Upload className="mx-auto mb-3 size-5 text-primary" aria-hidden="true" />
                  <Button variant="outline"  onClick={() => input.current?.click()}>Choose PDFs</Button>
                  <p className="mt-3 text-xs text-muted-foreground">Or drop it here · PDF · up to 10 MiB each</p>
                </div>
              ) : (
                <div className="flex flex-wrap justify-center gap-2">{suggestions.map(text => <Button key={text} variant="outline" className="h-auto whitespace-normal rounded-xl py-2"  onClick={() => onQuestionChange(text)}>{text}</Button>)}</div>
              )}
            </div>
    </ChatPanel>
  )

  return (
    <div className="flex h-dvh min-h-0 flex-col overflow-hidden bg-background text-foreground">
      <header className="flex h-16 shrink-0 items-center justify-between gap-3 border-b px-4">
        <div className="flex min-w-0 items-center gap-3">
          <Button variant="ghost" size="icon" aria-label={collapsed ? "Expand document sidebar" : "Collapse document sidebar"} aria-expanded={!collapsed} aria-controls="document-sidebar" onClick={() => setCollapsed(value => !value)}>{collapsed ? <PanelLeftOpen /> : <PanelLeftClose />}</Button>
          <span className="truncate text-base font-semibold tracking-tight">PDF RAG</span>
        </div>
        <ThemeToggle />
      </header>
      <div className="relative flex min-h-0 flex-1">
        {!collapsed && <aside id="document-sidebar" aria-label="Documents" className="absolute inset-y-0 left-0 z-20 flex w-64 shrink-0 flex-col border-r bg-card shadow-sm md:relative md:shadow-none">
          <div className="p-4"><Button className="w-full rounded-xl"  onClick={() => input.current?.click()}><Upload />Upload PDF</Button></div>
          <div className="px-4 pb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">Documents</div>
          <nav aria-label="Select a document" className="flex-1 space-y-1 overflow-y-auto px-2">{files.length ? files.map(file => (
            <DocumentItem key={file.id} file={file} selected={file.id === documentId} onRename={onRename} onDelete={deleteDocument} onSelect={() => { setNavigation(null); onSelectDocument(file.id); if (mobile) setCollapsed(true) }} />
          )) : <p className="px-3 py-4 text-sm text-muted-foreground">Your library starts here.</p>}</nav>
          <UploadList uploads={uploads} />
          <div className="border-t p-3"><Button variant="ghost" className="w-full justify-start" onClick={onLogout}><LogOut />Log out</Button></div>
        </aside>}
        {!collapsed && <button className="absolute inset-y-0 right-0 left-64 z-10 rounded-none! bg-black/20! p-0! md:hidden" aria-label="Close document sidebar" onClick={() => setCollapsed(true)} />}
        <input ref={input} className="hidden" type="file" multiple accept="application/pdf,.pdf" aria-label="Upload PDF" onChange={event => { upload(event.target.files); event.target.value = "" }} />
        <main className="min-w-0 flex-1" inert={mobile && !collapsed}>
          {!mobile ? <div className="h-full"><ResizablePanelGroup orientation="horizontal"><ResizablePanel id="pdf" defaultSize="45%" minSize="25%">{preview}</ResizablePanel><ResizableHandle withHandle aria-label="Resize PDF and chat panels" /><ResizablePanel id="chat" defaultSize="55%" minSize="30%">{chat}</ResizablePanel></ResizablePanelGroup></div> : <Tabs value={mobileTab} onValueChange={setMobileTab} className="flex h-full flex-col gap-0 md:hidden">
            <TabsList className="mx-4 my-3 grid w-auto grid-cols-2"><TabsTrigger value="chat">Chat</TabsTrigger><TabsTrigger value="pdf">PDF</TabsTrigger></TabsList>
            <TabsContent value="chat" className="min-h-0 flex-1">{chat}</TabsContent><TabsContent value="pdf" className="min-h-0 flex-1">{preview}</TabsContent>
          </Tabs>}
        </main>
      </div>
    </div>
  )
}
