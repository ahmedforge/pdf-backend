import { useEffect, useRef, useState, useSyncExternalStore } from "react"
import { FileText, LogOut, PanelLeftClose, PanelLeftOpen, Upload, MessageSquare, LoaderCircle } from "lucide-react"
import { apiRequest } from "@/api"
import { Button } from "@/components/ui/button"
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ChatPanel } from "@/components/chat-panel"
import { ThemeToggle } from "@/components/theme-toggle"

function subscribeMobile(callback) {
  const query = window.matchMedia("(max-width: 767px)")
  query.addEventListener("change", callback)
  return () => query.removeEventListener("change", callback)
}
const getMobileSnapshot = () => window.matchMedia("(max-width: 767px)").matches

function PdfPreview({ documentId, token, filename }) {
  const [preview, setPreview] = useState(null)
  useEffect(() => {
    if (!documentId) return
    const controller = new AbortController()
    let active = true
    let url
    apiRequest(`/download/${documentId}`, {
      headers: { Authorization: `Bearer ${token}` }, signal: controller.signal,
    }).then(response => response.blob()).then(blob => {
      if (!active) return
      url = URL.createObjectURL(blob)
      setPreview({ id: documentId, url })
    }).catch(error => {
      if (active && error.name !== "AbortError") setPreview({ id: documentId, error: error.message })
    })
    return () => {
      active = false
      controller.abort()
      if (url) URL.revokeObjectURL(url)
    }
  }, [documentId, token])

  return (
    <section className="flex h-full min-h-0 flex-col bg-muted/40" aria-label="PDF preview">
      <div className="flex h-14 shrink-0 items-center gap-2 border-b bg-background px-5 text-sm">
        <FileText className="size-4 text-muted-foreground" aria-hidden="true" />
        <span className="truncate">{filename || "PDF preview"}</span>
      </div>
      {!documentId ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center text-muted-foreground">
          <FileText className="size-10 stroke-1" aria-hidden="true" />
          <p className="text-sm">Your PDF will appear here.</p>
        </div>
      ) : preview?.id !== documentId ? (
        <div role="status" className="flex flex-1 items-center justify-center gap-2 text-sm text-muted-foreground"><LoaderCircle className="size-4" />Loading PDF…</div>
      ) : preview.error ? (
        <p role="alert" className="p-6 text-sm">Could not open PDF: {preview.error}</p>
      ) : (
        <iframe className="h-full min-h-0 w-full flex-1 border-0" src={preview.url} title={`PDF: ${filename || "selected document"}`} />
      )}
    </section>
  )
}

const suggestions = ["Summarize this document", "What are the key takeaways?", "Explain the main ideas simply"]

export function WorkspaceShell({ token, files, documentId, onSelectDocument, onUpload, onLogout, question, onQuestionChange, onAsk, turns, generating, onStop, onRetry, onClear, storageWarning, message, loading }) {
  const mobile = useSyncExternalStore(subscribeMobile, getMobileSnapshot, () => false)
  const [collapsed, setCollapsed] = useState(getMobileSnapshot)
  const [mobileTab, setMobileTab] = useState("chat")
  const [dragging, setDragging] = useState(false)
  const [uploadError, setUploadError] = useState("")
  const input = useRef(null)
  const selected = files.find(file => file.id === documentId)

  function upload(file) {
    if (!file || loading) return
    if (!/\.pdf$/i.test(file.name) || (file.type && file.type !== "application/pdf")) {
      setUploadError("Choose a PDF file.")
      return
    }
    if (file.size > 10 * 1024 * 1024) {
      setUploadError("Choose a PDF smaller than 10 MB.")
      return
    }
    setUploadError("")
    onUpload(file)
  }

  const preview = <PdfPreview documentId={documentId} token={token} filename={selected?.filename} />
  const chat = (
    <ChatPanel key={documentId || 'empty'} documentId={documentId} turns={turns} question={question}
      onQuestionChange={onQuestionChange} onAsk={onAsk} onRetry={onRetry} onStop={onStop}
      generating={generating} loading={loading} message={uploadError || message} onClear={onClear} storageWarning={storageWarning}>
            <div className="fade-in flex min-h-64 flex-col items-center justify-center gap-4 text-center">
              <div className="rounded-xl border bg-card p-3 shadow-xs"><MessageSquare className="size-5 text-primary" aria-hidden="true" /></div>
              <h2 className="m-0 text-xl font-medium">A little clarity, one question at a time.</h2>
              <p className="max-w-sm text-sm text-muted-foreground">{documentId ? "Ask about your document or start with a suggestion." : "Upload a PDF to explore its ideas."}</p>
              {!documentId ? (
                <div className={`w-full max-w-sm rounded-xl border border-dashed p-7 ${dragging ? "bg-accent" : "bg-card"}`}
                  onDragOver={event => { event.preventDefault(); setDragging(true) }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={event => { event.preventDefault(); setDragging(false); upload(event.dataTransfer.files[0]) }}>
                  <Upload className="mx-auto mb-3 size-5 text-primary" aria-hidden="true" />
                  <Button variant="outline" disabled={loading || generating} onClick={() => input.current?.click()}>Choose a PDF</Button>
                  <p className="mt-3 text-xs text-muted-foreground">Or drop it here · PDF up to 10 MB</p>
                </div>
              ) : (
                <div className="flex flex-wrap justify-center gap-2">{suggestions.map(text => <Button key={text} variant="outline" className="h-auto whitespace-normal rounded-xl py-2" disabled={loading} onClick={() => onQuestionChange(text)}>{text}</Button>)}</div>
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
          <div className="p-4"><Button className="w-full rounded-xl" disabled={loading || generating} onClick={() => input.current?.click()}><Upload />Upload PDF</Button></div>
          <div className="px-4 pb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">Documents</div>
          <nav aria-label="Select a document" className="flex-1 space-y-1 overflow-y-auto px-2">{files.length ? files.map(file => (
            <Button key={file.id} variant="ghost" className={`h-auto w-full justify-start rounded-xl px-3 py-3 text-left ${file.id === documentId ? "bg-accent text-accent-foreground" : ""}`} aria-current={file.id === documentId ? "true" : undefined} disabled={loading} title={file.filename} onClick={() => { onSelectDocument(file.id); if (window.matchMedia("(max-width: 767px)").matches) setCollapsed(true) }}><FileText className="size-4 shrink-0" /><span className="truncate">{file.filename}</span></Button>
          )) : <p className="px-3 py-4 text-sm text-muted-foreground">Your library starts here.</p>}</nav>
          <div className="border-t p-3"><Button variant="ghost" className="w-full justify-start" onClick={onLogout}><LogOut />Log out</Button></div>
        </aside>}
        {!collapsed && <button className="absolute inset-y-0 right-0 left-64 z-10 rounded-none! bg-black/20! p-0! md:hidden" aria-label="Close document sidebar" onClick={() => setCollapsed(true)} />}
        <input ref={input} className="hidden" type="file" accept="application/pdf,.pdf" aria-label="Upload PDF" onChange={event => { upload(event.target.files[0]); event.target.value = "" }} />
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
